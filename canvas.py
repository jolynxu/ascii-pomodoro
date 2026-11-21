"""A full-screen drawing surface with real colors and glow.

Every cell has a character, a text color and a background color. Glow works
by *adding* light to the background colors around a point, so overlapping
glows blend together like real light.

The Renderer only redraws cells that changed since the last frame, which
keeps the amount of text sent to the terminal small.
"""

import os
import unicodedata

ASPECT = 2.1  # terminal characters are about twice as tall as wide


# ---------------------------------------------------------------- color helpers
# Colors are (r, g, b) tuples with values 0-255 (floats are fine).

def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def scale(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def ramp(stops, v):
    """Pick a color along a gradient. stops = [(position, color), ...]."""
    if v <= stops[0][0]:
        return stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if v <= p1:
            return lerp(c0, c1, (v - p0) / (p1 - p0))
    return stops[-1][1]


def pack(c):
    r, g, b = c
    r = 0 if r < 0 else 255 if r > 255 else int(r)
    g = 0 if g < 0 else 255 if g > 255 else int(g)
    b = 0 if b < 0 else 255 if b > 255 else int(b)
    return r << 16 | g << 8 | b


def unpack(p):
    return (p >> 16) & 255, (p >> 8) & 255, p & 255


def supports_truecolor():
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return True
    return os.environ.get("TERM_PROGRAM") in ("iTerm.app", "WezTerm", "vscode", "ghostty")


# ---------------------------------------------------------------- canvas

_kernels = {}


def _kernel(radius):
    """Offsets and weights for a soft round glow (round on screen, not in cells)."""
    key = round(radius * 2) / 2
    if key not in _kernels:
        r = max(0.5, key)
        pts = []
        for dy in range(-int(r), int(r) + 1):
            for dx in range(-int(r * ASPECT), int(r * ASPECT) + 1):
                d = ((dx / ASPECT) ** 2 + dy * dy) ** 0.5 / (r + 0.5)
                if d < 1:
                    pts.append((dx, dy, (1 - d) ** 2))
        _kernels[key] = pts
    return _kernels[key]


class Canvas:
    def __init__(self, w, h, base=(0, 0, 0)):
        self.w, self.h = w, h
        n = w * h
        self.ch = [" "] * n
        self.fg = [0xFFFFFF] * n
        self.br = [float(base[0])] * n   # background red, green, blue
        self.bg = [float(base[1])] * n
        self.bb = [float(base[2])] * n
        self.glow_on = True

    def put(self, x, y, ch, color):
        x, y = int(x + 0.5), int(y + 0.5)
        if 0 <= x < self.w and 0 <= y < self.h:
            i = y * self.w + x
            self.ch[i] = ch
            self.fg[i] = pack(color)

    def set_bg(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = y * self.w + x
            self.br[i], self.bg[i], self.bb[i] = c

    def add_bg(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = y * self.w + x
            self.br[i] += c[0]
            self.bg[i] += c[1]
            self.bb[i] += c[2]

    def glow(self, x, y, color, radius, strength=1.0):
        """Add a soft halo of light centred on (x, y)."""
        if not self.glow_on or strength <= 0:
            return
        x, y = int(x + 0.5), int(y + 0.5)
        w, h = self.w, self.h
        r, g, b = color[0] * strength, color[1] * strength, color[2] * strength
        br, bg, bb = self.br, self.bg, self.bb
        for dx, dy, k in _kernel(radius):
            xx, yy = x + dx, y + dy
            if 0 <= xx < w and 0 <= yy < h:
                i = yy * w + xx
                br[i] += r * k
                bg[i] += g * k
                bb[i] += b * k

    def dim_rect(self, x, y, w, h, k):
        """Erase characters in a box and darken its background (for text)."""
        for yy in range(max(0, y), min(self.h, y + h)):
            for xx in range(max(0, x), min(self.w, x + w)):
                i = yy * self.w + xx
                self.ch[i] = " "
                self.br[i] *= k
                self.bg[i] *= k
                self.bb[i] *= k

    def dim_row(self, y, k):
        """Darken a whole row, art and all (for fading under the bottom bar)."""
        if not 0 <= y < self.h:
            return
        a, b = y * self.w, (y + 1) * self.w
        self.br[a:b] = [v * k for v in self.br[a:b]]
        self.bg[a:b] = [v * k for v in self.bg[a:b]]
        self.bb[a:b] = [v * k for v in self.bb[a:b]]
        self.fg[a:b] = [pack(scale(unpack(c), k)) for c in self.fg[a:b]]

    def fade(self, k):
        """Darken everything (used for fading scenes in)."""
        self.br = [v * k for v in self.br]
        self.bg = [v * k for v in self.bg]
        self.bb = [v * k for v in self.bb]
        self.fg = [pack(scale(unpack(c), k)) for c in self.fg]

    def edge_color(self):
        """Average background color around the outside of the screen."""
        w, h = self.w, self.h
        idx = list(range(w)) + [i * w for i in range(1, h)] + [i * w + w - 1 for i in range(1, h)]
        n = len(idx)
        return (sum(self.br[i] for i in idx) / n, sum(self.bg[i] for i in idx) / n,
                sum(self.bb[i] for i in idx) / n)

    def text(self, x, y, s, color):
        for ch in s:
            wide = unicodedata.east_asian_width(ch) in "WF"
            self.put(x, y, ch, color)
            if wide:  # takes two cells: leave the second one empty
                self.put(x + 1, y, "", color)
            x += 2 if wide else 1

    def center(self, y, s, color, dim=1.0):
        s = s[: max(0, self.w - 2)]
        x = (self.w - len(s)) // 2
        self.dim_rect(x, y, len(s), 1, dim)
        self.text(x, y, s, color)

    def soft_shade(self, cx, cy, rx, ry, k):
        """Darken an oval area, strongest in the middle and fading to nothing
        at the edge (so there's no hard box), to keep text readable."""
        for y in range(max(0, int(cy - ry)), min(self.h, int(cy + ry) + 1)):
            dy = (y - cy) / ry
            for x in range(max(0, int(cx - rx)), min(self.w, int(cx + rx) + 1)):
                dx = (x - cx) / rx
                d2 = dx * dx + dy * dy
                if d2 >= 1:
                    continue
                f = 1 - k * (1 - d2) ** 1.5
                i = y * self.w + x
                self.br[i] *= f
                self.bg[i] *= f
                self.bb[i] *= f
                if self.ch[i] != " ":
                    self.fg[i] = pack(scale(unpack(self.fg[i]), f * f))


# ---------------------------------------------------------------- terminal output

def _to_256(r, g, b):
    levels = (0, 95, 135, 175, 215, 255)

    def nearest(v):
        return min(range(6), key=lambda i: abs(levels[i] - v))

    ri, gi, bi = nearest(r), nearest(g), nearest(b)
    cube = (levels[ri], levels[gi], levels[bi])
    gray_i = max(0, min(23, round((r + g + b) / 3 - 8) // 10))
    gray = 8 + gray_i * 10
    d_cube = sum((a - c) ** 2 for a, c in zip((r, g, b), cube))
    d_gray = sum((a - gray) ** 2 for a in (r, g, b))
    if d_gray < d_cube:
        return 232 + gray_i
    return 16 + 36 * ri + 6 * gi + bi


class Renderer:
    def __init__(self, truecolor=True):
        self.truecolor = truecolor
        self.reset()

    def reset(self):
        """Forget the last frame so the next one is drawn in full."""
        self.prev = None
        self.codes = {}

    def _code(self, layer, c):
        key = (layer, c)
        s = self.codes.get(key)
        if s is None:
            r, g, b = unpack(c)
            if self.truecolor:
                s = f"\033[{layer};2;{r};{g};{b}m"
            else:
                s = f"\033[{layer};5;{_to_256(r, g, b)}m"
            self.codes[key] = s
        return s

    def render(self, cv):
        w, n = cv.w, cv.w * cv.h
        chs = cv.ch
        # round colors a little so tiny changes don't force a redraw
        bgs = [(int(min(r, 255.0)) & 0xF8) << 16 | (int(min(g, 255.0)) & 0xF8) << 8
               | (int(min(b, 255.0)) & 0xF8) for r, g, b in zip(cv.br, cv.bg, cv.bb)]
        fgs = [f & 0xFCFCFC if c != " " else -1 for c, f in zip(chs, cv.fg)]

        prev = self.prev if self.prev and self.prev[0] == (w, cv.h) else None
        out = [] if prev else ["\033[0m\033[2J"]
        if prev:
            _, pch, pfg, pbg = prev
        cur_fg = cur_bg = None
        cursor = -1
        for i in range(n):
            ch, bg, fg = chs[i], bgs[i], fgs[i]
            if prev and ch == pch[i] and bg == pbg[i] and fg == pfg[i]:
                continue
            if ch == "":  # right half of a wide character
                cursor = -1
                continue
            if i != cursor:
                out.append(f"\033[{i // w + 1};{i % w + 1}H")
            if bg != cur_bg:
                out.append(self._code(48, bg))
                cur_bg = bg
            if fg != -1 and fg != cur_fg:
                out.append(self._code(38, fg))
                cur_fg = fg
            out.append(ch)
            nxt = i + 1
            cursor = nxt if nxt % w and (nxt >= n or chs[nxt] != "") else -1
        self.prev = ((w, cv.h), chs, fgs, bgs)
        return "".join(out)
