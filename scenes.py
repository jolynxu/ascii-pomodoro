"""The space backgrounds. Each scene draws itself onto a Canvas every frame.

    planet     a ringed gas giant with a glowing atmosphere and a moon
    constellations  glowing star patterns that trace themselves in, one by one
    blackhole  a black hole with a swirling, glowing accretion disk
    warp       flying through space at warp speed
    galaxy     a slowly turning spiral galaxy
    sun        a boiling star with a corona and solar flares
    orbit      low Earth orbit: city lights, aurora, a satellite, a Starlink train
    pulsar     a spinning neutron star sweeping lighthouse beams
    comet      a comet with a blue ion tail and a curved dust tail
    aurora     the northern lights over mountains and a still lake
    nebula     the Eagle Nebula's Pillars of Creation, glowing where starlight hits them
"""

import math
import random

from canvas import ASPECT, lerp, pack, ramp, scale

TAU = math.tau
RAMP = " .:-=+*#%@"           # dark -> bright shading characters
LIGHT = (-0.6, -0.5, 0.62)    # light comes from the upper left

HEAT = [(0.0, (40, 4, 0)), (0.3, (200, 50, 10)), (0.55, (255, 140, 30)),
        (0.8, (255, 215, 130)), (1.0, (255, 252, 240))]


def layout(cv):
    """Centre point and half-height of the whole window (the art fills it,
    and the clock floats on top)."""
    return cv.w / 2, cv.h * 0.54, cv.h * 0.48


def shade_char(v):
    return RAMP[max(0, min(len(RAMP) - 1, int(v * len(RAMP))))]


# ---------------------------------------------------------------- shared pieces

_noise_cache = {}


def noise_texture(w=192, h=96, cells=6, octaves=4, seed=1):
    """Smooth random values 0-1 that wrap around at the edges (cached)."""
    key = (w, h, cells, octaves, seed)
    if key in _noise_cache:
        return _noise_cache[key]
    rnd = random.Random(seed)
    out = [[0.0] * w for _ in range(h)]
    amp = 1.0
    for o in range(octaves):
        gx, gy = cells * 2 ** o, max(1, cells * h // w) * 2 ** o
        grid = [[rnd.random() for _ in range(gx)] for _ in range(gy)]
        for y in range(h):
            fy = y * gy / h
            y0 = int(fy)
            ty = fy - y0
            ty = ty * ty * (3 - 2 * ty)
            r0, r1, orow = grid[y0], grid[(y0 + 1) % gy], out[y]
            for x in range(w):
                fx = x * gx / w
                x0 = int(fx)
                tx = fx - x0
                tx = tx * tx * (3 - 2 * tx)
                x1 = (x0 + 1) % gx
                a = r0[x0] + (r0[x1] - r0[x0]) * tx
                b = r1[x0] + (r1[x1] - r1[x0]) * tx
                orow[x] += (a + (b - a) * ty) * amp
        amp *= 0.5
    lo = min(map(min, out))
    hi = max(map(max, out))
    out = [[(v - lo) / (hi - lo) for v in row] for row in out]
    _noise_cache[key] = out
    return out


def sample(tex, u, v):
    """Look up a noise texture with wrap-around coordinates (0-1 = one tile)."""
    return tex[int(v * len(tex)) % len(tex)][int(u * len(tex[0])) % len(tex[0])]


STAR_COLORS = [(170, 190, 255), (210, 220, 255), (255, 255, 255),
               (255, 240, 210), (255, 210, 160)]


class Stars:
    """Twinkling background stars, plus the odd shooting star."""

    def __init__(self, count=160, brightness=1.0, meteors=0.012):
        self.brightness = brightness
        self.shooting = ShootingStars(meteors)
        self.stars = [(random.random(), random.random(), random.uniform(0.8, 4),
                       random.uniform(0, TAU), random.random() ** 4,
                       random.choice(STAR_COLORS)) for _ in range(count)]

    def draw(self, cv, t):
        for x, y, speed, phase, mag, col in self.stars:
            tw = 0.5 + 0.5 * math.sin(t * speed + phase)
            b = (0.25 + 0.5 * mag + 0.35 * tw * (0.4 + mag)) * self.brightness
            ch = "*" if b > 0.95 else "+" if b > 0.7 else "." if b > 0.3 else "·"
            px, py = x * cv.w, y * cv.h
            cv.put(px, py, ch, scale(col, min(1.0, b)))
            if mag > 0.35:
                cv.glow(px, py, col, 1.2, 0.18 * b)
        self.shooting.draw(cv)


class ShootingStars:
    def __init__(self, chance=0.012):
        self.chance = chance
        self.active = []  # [x, y, dx, dy, frames_left]

    def draw(self, cv):
        if random.random() < self.chance:
            self.active.append([random.uniform(0, cv.w * 0.6), random.uniform(0, cv.h * 0.35),
                                random.uniform(1.5, 2.5), random.uniform(0.4, 0.8), 40])
        for s in self.active:
            s[0] += s[2]
            s[1] += s[3]
            s[4] -= 1
            for k in range(8):
                fade = 1 - k / 8
                col = lerp((80, 90, 200), (255, 255, 255), fade)
                cv.put(s[0] - s[2] * k * 0.6, s[1] - s[3] * k * 0.6, "*" if k == 0 else ".",
                       scale(col, fade))
            cv.glow(s[0], s[1], (150, 190, 255), 2, 0.35)
        self.active = [s for s in self.active if s[4] > 0]


def sprite(cv, x, y, rows, palette):
    """Draw pixel art with square pixels: each text cell holds two pixels,
    one above the other (using half blocks). rows is a list of strings, one
    letter per pixel, looked up in palette; '.' is see-through."""
    for r in range(0, len(rows), 2):
        top = rows[r]
        bottom = rows[r + 1] if r + 1 < len(rows) else "." * len(top)
        for i, (a, b) in enumerate(zip(top, bottom)):
            cx, cy = x + i, y + r // 2
            if a != "." and b != ".":
                cv.put(cx, cy, "▀", palette[a])
                cv.set_bg(int(cx + 0.5), int(cy + 0.5), palette[b])
            elif a != ".":
                cv.put(cx, cy, "▀", palette[a])
            elif b != ".":
                cv.put(cx, cy, "▄", palette[b])


def space_gradient(cv, top=(2, 3, 14), bottom=(8, 4, 22)):
    """Fill the background with a soft vertical gradient."""
    w = cv.w
    for y in range(cv.h):
        r, g, b = lerp(top, bottom, y / max(1, cv.h - 1))
        cv.br[y * w:(y + 1) * w] = [r] * w
        cv.bg[y * w:(y + 1) * w] = [g] * w
        cv.bb[y * w:(y + 1) * w] = [b] * w


# ---------------------------------------------------------------- 1. ringed planet

class RingedPlanet:
    name = "Ringed Planet"
    BANDS = [(0.0, (110, 60, 30)), (0.25, (175, 105, 55)), (0.45, (215, 160, 95)),
             (0.6, (240, 205, 150)), (0.8, (200, 130, 75)), (1.0, (150, 85, 45))]

    def __init__(self):
        self.stars = Stars(150)

    def draw(self, cv, t):
        space_gradient(cv)
        self.stars.draw(cv, t)

        cx, cy, half = layout(cv)
        R = max(2.5, min(half * 0.62, cv.w / ASPECT * 0.2))

        ma = t * 0.4
        moon = (cx + math.cos(ma) * 2.5 * R * ASPECT, cy + math.sin(ma) * 2.5 * R * 0.45,
                max(1.2, R * 0.28))
        moon_front = math.sin(ma) > 0

        cv.glow(cx, cy, (255, 150, 70), R * 2.2, 0.16)   # warm haze around the planet
        if not moon_front:
            self._moon(cv, *moon)
        self._ring(cv, t, cx, cy, R, front=False)
        self._planet(cv, t, cx, cy, R)
        self._ring(cv, t, cx, cy, R, front=True)
        if moon_front:
            self._moon(cv, *moon)

    def _planet(self, cv, t, cx, cy, r):
        spin = t * 0.5
        for y in range(int(cy - r * 1.3) - 1, int(cy + r * 1.3) + 2):
            for x in range(int(cx - r * 1.3 * ASPECT) - 1, int(cx + r * 1.3 * ASPECT) + 2):
                px, py = (x - cx) / (r * ASPECT), (y - cy) / r
                d2 = px * px + py * py
                if d2 > 1:
                    d = math.sqrt(d2)
                    if d < 1.3:  # thin glowing atmosphere around the edge
                        cv.add_bg(x, y, scale((255, 170, 90), 70 * (1.3 - d) / 0.3 / 255))
                    continue
                pz = math.sqrt(1 - d2)
                b = max(0.0, px * LIGHT[0] + py * LIGHT[1] + pz * LIGHT[2])
                lon = math.atan2(px, pz) + spin
                stripe = math.sin(py * 9 + 0.6 * math.sin(lon * 2 + py * 4))
                col = ramp(self.BANDS, (stripe + 1) / 2)
                lit = 0.12 + 0.95 * b
                rim = (1 - pz) ** 3 * 0.6   # edges glow a little
                cv.put(x, y, shade_char(b * 0.95 + 0.05), scale(col, lit + rim))
                cv.set_bg(x, y, scale(col, 0.3 * lit + rim * 0.4))

    def _moon(self, cv, mx, my, mr):
        for y in range(int(my - mr) - 1, int(my + mr) + 2):
            for x in range(int(mx - mr * ASPECT) - 1, int(mx + mr * ASPECT) + 2):
                px, py = (x - mx) / (mr * ASPECT), (y - my) / mr
                d2 = px * px + py * py
                if d2 > 1:
                    continue
                pz = math.sqrt(1 - d2)
                b = max(0.0, px * LIGHT[0] + py * LIGHT[1] + pz * LIGHT[2])
                col = scale((210, 215, 230), 0.15 + 0.9 * b)
                cv.put(x, y, shade_char(b), col)
                cv.set_bg(x, y, scale(col, 0.25))
        cv.glow(mx, my, (160, 180, 255), mr * 2, 0.12)

    def _ring(self, cv, t, cx, cy, R, front, tilt=0.35):
        for y in range(int(cy - 2.2 * R * tilt) - 1, int(cy + 2.2 * R * tilt) + 2):
            for x in range(int(cx - 2.2 * R * ASPECT), int(cx + 2.2 * R * ASPECT) + 1):
                u, v = (x - cx) / ASPECT, (y - cy) / tilt
                r = math.hypot(u, v) / R
                if not 1.35 < r < 2.1 or 1.74 < r < 1.82 or (v > 0) != front:
                    continue
                sparkle = int(math.atan2(v, u) * 20 - t * 4 + r * 7) % 9 == 0
                if r < 1.55:
                    ch, col = ":", (255, 220, 170)
                elif r < 1.74:
                    ch, col = "=", (220, 170, 110)
                else:
                    ch, col = "-", (170, 150, 120)
                if sparkle:
                    ch, col = ".", (255, 250, 230)
                cv.put(x, y, ch, col)
                cv.add_bg(x, y, scale(col, 0.12))


# ---------------------------------------------------------------- 2. constellations

BLUE_STAR, WHITE_STAR, GOLD_STAR, RED_STAR = (170, 200, 255), (235, 240, 255), (255, 225, 160), (255, 140, 90)

# name, where it sits (centre x, centre y, size as a fraction of the screen
# height), stars (x, y, brightness 0-1, color) and the lines joining them.
CONSTELLATIONS = [
    ("big dipper", (0.16, 0.2, 0.3),
     [(1.0, 0.0, 0.8, WHITE_STAR), (1.0, 0.36, 0.7, WHITE_STAR), (0.72, 0.46, 0.6, WHITE_STAR),
      (0.67, 0.16, 0.45, WHITE_STAR), (0.44, 0.12, 0.75, WHITE_STAR),
      (0.24, 0.16, 0.7, WHITE_STAR), (0.0, 0.34, 0.75, BLUE_STAR)],
     [(0, 1), (1, 2), (2, 3), (3, 0), (3, 4), (4, 5), (5, 6)]),
    ("cassiopeia", (0.86, 0.17, 0.2),
     [(0.0, 0.1, 0.7, WHITE_STAR), (0.25, 0.5, 0.6, WHITE_STAR), (0.5, 0.2, 0.8, GOLD_STAR),
      (0.76, 0.55, 0.6, WHITE_STAR), (1.0, 0.05, 0.7, WHITE_STAR)],
     [(0, 1), (1, 2), (2, 3), (3, 4)]),
    ("orion", (0.52, 0.62, 0.4),
     [(0.0, 0.0, 1.0, RED_STAR), (0.55, 0.06, 0.75, BLUE_STAR), (0.27, -0.2, 0.45, BLUE_STAR),
      (0.21, 0.45, 0.7, BLUE_STAR), (0.3, 0.42, 0.75, BLUE_STAR), (0.39, 0.39, 0.7, BLUE_STAR),
      (0.06, 0.86, 0.65, BLUE_STAR), (0.64, 0.8, 1.0, BLUE_STAR),
      (0.31, 0.6, 0.35, (255, 170, 230))],   # the Orion nebula in the sword
     [(0, 2), (2, 1), (0, 3), (1, 5), (3, 4), (4, 5), (3, 6), (5, 7), (4, 8)]),
    ("cygnus", (0.15, 0.62, 0.34),
     [(0.5, 0.0, 0.9, WHITE_STAR), (0.5, 0.38, 0.7, GOLD_STAR), (0.5, 1.0, 0.6, GOLD_STAR),
      (0.08, 0.3, 0.6, WHITE_STAR), (0.95, 0.5, 0.6, WHITE_STAR), (0.5, 0.7, 0.4, WHITE_STAR)],
     [(0, 1), (1, 5), (5, 2), (3, 1), (1, 4)]),
    ("lyra", (0.33, 0.42, 0.16),
     [(0.3, 0.0, 1.0, (200, 220, 255)), (0.42, 0.35, 0.5, WHITE_STAR), (0.72, 0.4, 0.5, WHITE_STAR),
      (0.66, 0.9, 0.5, WHITE_STAR), (0.36, 0.84, 0.5, WHITE_STAR)],
     [(0, 1), (1, 2), (2, 3), (3, 4), (4, 1)]),
    ("scorpius", (0.82, 0.6, 0.42),
     [(0.0, 0.0, 0.6, WHITE_STAR), (0.08, 0.16, 0.65, BLUE_STAR), (0.02, 0.33, 0.55, WHITE_STAR),
      (0.26, 0.3, 1.0, RED_STAR), (0.36, 0.46, 0.55, WHITE_STAR), (0.42, 0.64, 0.55, WHITE_STAR),
      (0.48, 0.84, 0.6, WHITE_STAR), (0.64, 0.97, 0.65, WHITE_STAR), (0.84, 0.94, 0.65, WHITE_STAR),
      (0.95, 0.8, 0.6, BLUE_STAR), (0.9, 0.68, 0.8, BLUE_STAR)],
     [(0, 1), (1, 2), (1, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10)]),
]


class Constellations:
    name = "Constellations"
    TURN = 9.0   # seconds each constellation spends in the spotlight

    def __init__(self):
        self.stars = Stars(150, brightness=0.55)
        self.size = None

    def _prepare(self, w, h):
        """Background with a faint milky way across it, once per screen size."""
        tex = noise_texture(seed=31, cells=6, octaves=5)
        self.BR, self.BG, self.BB = [], [], []
        for y in range(h):
            top = lerp((2, 3, 14), (6, 6, 24), y / max(1, h - 1))
            for x in range(w):
                u, v = x / w, y / h
                d = (v - (0.95 - 0.8 * u)) * 2.2          # distance from the band
                n = sample(tex, u * 1.3, v * 0.7)
                band = math.exp(-(d / 0.35) ** 2) * (0.3 + 0.9 * n ** 2)
                self.BR.append(top[0] + 34 * band)
                self.BG.append(top[1] + 26 * band)
                self.BB.append(top[2] + 52 * band)
        # each constellation's stars in screen cells
        self.placed = []
        for name, (fx, fy, size), stars, lines in CONSTELLATIONS:
            xs, ys = [s[0] for s in stars], [s[1] for s in stars]
            mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            S = size * h
            pts = [(fx * w + (x - mx) * S * ASPECT, fy * h + (y - my) * S, b, c)
                   for x, y, b, c in stars]
            bottom = max(p[1] for p in pts)
            self.placed.append((name, pts, lines, fx * w, bottom + 2))
        self.size = (w, h)

    def draw(self, cv, t):
        if self.size != (cv.w, cv.h):
            self._prepare(cv.w, cv.h)
        cv.br, cv.bg, cv.bb = self.BR[:], self.BG[:], self.BB[:]
        self.stars.draw(cv, t)
        n = len(self.placed)
        turn = (t / self.TURN) % n
        for k, (name, pts, lines, lx, ly) in enumerate(self.placed):
            age = (turn - k) % n                         # 0-1 while it's in the spotlight
            spot = math.sin(age * math.pi) if age < 1 else 0.0
            trace = min(1.0, age * 2.2) if age < 1 else 1.0
            self._lines(cv, t, pts, lines, spot, trace)
            for i, (x, y, b, col) in enumerate(pts):
                tw = 0.85 + 0.15 * math.sin(t * (1.3 + i * 0.37) + k)
                lit = (0.55 + 0.45 * b) * tw * (0.8 + 0.4 * spot)
                cv.glow(x, y, col, 1 + 1.2 * b, (0.2 + 0.35 * spot) * b)
                cv.put(x, y, "✦" if b > 0.85 else "*" if b > 0.55 else "+",
                       lerp(col, (255, 255, 255), 0.3 * lit))
            if spot > 0.15:
                label = "  ".join(name.split())
                label = " ".join(label)
                cv.text(lx - len(label) / 2, ly, label, scale((150, 175, 255), spot * 0.85))

    @staticmethod
    def _lines(cv, t, pts, lines, spot, trace):
        """Dotted glowing lines. In the spotlight they trace themselves in one by
        one, with a spark of light at the tip, then light pulses run along them."""
        m = len(lines)
        for j, (a, b) in enumerate(lines):
            x0, y0, _, _ = pts[a]
            x1, y1, _, _ = pts[b]
            part = min(1.0, max(0.0, trace * m - j)) if spot > 0 else 1.0
            if part <= 0:
                continue
            dx, dy = x1 - x0, y1 - y0
            steps = int(max(abs(dx), abs(dy))) + 1
            base = 0.4 + 0.55 * spot
            pulse_at = ((t * 0.5 + j * 0.31) % 1.6) * steps
            for s in range(1, int(steps * part)):
                f = s / steps
                x, y = x0 + dx * f, y0 + dy * f
                shine = math.exp(-((s - pulse_at) / 1.5) ** 2) * (0.3 + 0.7 * spot)
                col = lerp((90, 120, 230), (210, 225, 255), shine)
                cv.put(x, y, "·", scale(col, min(1.0, base + shine)))
                cv.add_bg(int(x + 0.5), int(y + 0.5), scale((25, 38, 110), 0.15 + 0.6 * spot + shine))
            if 0 < part < 1:                         # the tip still drawing
                x, y = x0 + dx * part, y0 + dy * part
                cv.glow(x, y, (180, 210, 255), 1.5, 0.7)
                cv.put(x, y, "•", (255, 255, 255))


# ---------------------------------------------------------------- 3. black hole

class BlackHole:
    name = "Black Hole"
    DISK = [(0.0, (60, 10, 0)), (0.3, (230, 80, 15)), (0.6, (255, 170, 70)),
            (0.85, (255, 230, 180)), (1.0, (255, 255, 250))]

    def __init__(self):
        self.stars = Stars(170, brightness=0.8)

    def draw(self, cv, t):
        space_gradient(cv, (1, 1, 6), (3, 1, 8))
        self.stars.draw(cv, t)
        cx, cy, half = layout(cv)
        R = max(2.0, min(half * 0.55, cv.w / ASPECT * 0.11))  # size of the shadow
        rin, rout, tilt = 1.5, 4.3, 0.2

        cv.glow(cx, cy, (255, 110, 40), R * 3.2, 0.22)
        sin, cos, atan2, hypot = math.sin, math.cos, math.atan2, math.hypot
        ylo = int(cy - max(rout * R * tilt, 1.8 * R)) - 1
        yhi = int(cy + max(rout * R * tilt, 1.8 * R)) + 2
        for y in range(ylo, yhi):
            for x in range(int(cx - rout * R * ASPECT) - 1, int(cx + rout * R * ASPECT) + 2):
                u, v = (x - cx) / ASPECT / R, (y - cy) / R
                d = hypot(u, v)
                val = 0.0
                rd = hypot(u, v / tilt)
                if rin < rd < rout and (v > 0 or d > 1.0):
                    # the flat disk; inner parts orbit faster
                    ang = atan2(v / tilt, u)
                    heat = (1 - (rd - rin) / (rout - rin)) ** 1.4
                    swirl = 0.55 + 0.45 * sin(ang * 5 + rd * 4 - t * 6 / rd ** 1.5)
                    doppler = 1 - 0.55 * cos(ang)       # the side coming at us is brighter
                    val = 1.35 * heat * swirl * doppler
                elif 1.0 < d < 1.6:
                    # light from the far side, bent up and over the hole
                    ang = atan2(v, u)
                    fall = (1.6 - d) / 0.6
                    swirl = 0.6 + 0.4 * sin(ang * 4 - t * 3)
                    val = fall ** 2 * swirl * (1 - 0.5 * cos(ang)) * 0.85
                    if d < 1.09:
                        val = max(val, 0.95)   # thin photon ring
                elif d <= 1.0:
                    cv.set_bg(x, y, (0, 0, 0))
                    cv.put(x, y, " ", (0, 0, 0))
                    continue
                if val > 0.04:
                    v1 = min(1.0, val)
                    col = ramp(self.DISK, v1)
                    cv.put(x, y, shade_char(v1), col)
                    cv.add_bg(x, y, scale(col, 0.35 * v1))


# ---------------------------------------------------------------- 4. warp

class Warp:
    name = "Warp Speed"

    def __init__(self):
        self.stars = [self._new(random.random()) for _ in range(230)]
        self.last = None

    @staticmethod
    def _new(z):
        a, r = random.uniform(0, TAU), random.uniform(0.04, 1.0)
        tint = random.choice([(140, 170, 255), (190, 140, 255), (140, 240, 255),
                              (255, 255, 255)])
        return [math.cos(a) * r, math.sin(a) * r, z, tint]

    def draw(self, cv, t):
        dt = 0.05 if self.last is None else max(0.0, min(0.1, t - self.last))
        self.last = t
        space_gradient(cv, (1, 2, 10), (1, 2, 10))
        cx, cy = cv.w / 2, cv.h * 0.55
        size = min(cv.w / ASPECT, cv.h) * 0.6
        jump = max(0.0, math.sin(t * 0.22)) ** 8        # every so often: hyperjump
        speed = 0.22 + 1.1 * jump

        cv.glow(cx, cy, (40, 60, 200), cv.h * 0.45, 0.35 + 0.5 * jump)
        cv.glow(cx, cy, (180, 120, 255), cv.h * 0.18, 0.25 + 0.6 * jump)

        for s in self.stars:
            s[2] -= speed * dt
            if s[2] <= 0.03:
                s[:] = self._new(1.0)
            hx, hy = cx + s[0] / s[2] * size * ASPECT, cy + s[1] / s[2] * size
            zt = min(1.0, s[2] + 0.03 + speed * 0.12)
            tx, ty = cx + s[0] / zt * size * ASPECT, cy + s[1] / zt * size
            near = (1 - s[2]) ** 1.6
            self._streak(cv, tx, ty, hx, hy, s[3], near)
            if near > 0.6:
                cv.glow(hx, hy, s[3], 1.5, 0.3 * near)

    @staticmethod
    def _streak(cv, x0, y0, x1, y1, tint, near):
        dx, dy = x1 - x0, y1 - y0
        steps = int(max(abs(dx), abs(dy))) + 1
        if steps > 60:
            return
        ang = math.atan2(dy * ASPECT, dx)
        c, s = abs(math.cos(ang)), abs(math.sin(ang))
        ch = "-" if c > 0.92 else "|" if s > 0.92 else ("\\" if dx * dy > 0 else "/")
        for k in range(steps + 1):
            f = k / steps
            col = scale(lerp((30, 40, 120), tint, f), 0.3 + 0.7 * near)
            cv.put(x0 + dx * f, y0 + dy * f, ch, col)
        cv.put(x1, y1, "*" if near > 0.7 else "+" if near > 0.35 else ".",
               lerp(tint, (255, 255, 255), near))


# ---------------------------------------------------------------- 5. galaxy

class Galaxy:
    name = "Spiral Galaxy"

    def __init__(self):
        self.stars = Stars(110, brightness=0.75)

    def draw(self, cv, t):
        space_gradient(cv, (1, 1, 8), (4, 2, 12))
        self.stars.draw(cv, t)
        cx, cy, half = layout(cv)
        tilt = 0.5
        G = max(4.0, min(half * 1.15 / tilt, cv.w * 0.5 / ASPECT))  # galaxy radius
        tex = noise_texture(seed=3, cells=8, octaves=3)
        rot = t * 0.06
        sin, cos, exp, log, atan2 = math.sin, math.cos, math.exp, math.log, math.atan2

        cv.glow(cx, cy, (255, 200, 140), G * tilt * 0.9, 0.35)
        for y in range(int(cy - G * tilt) - 1, int(cy + G * tilt) + 2):
            for x in range(int(cx - G * ASPECT) - 1, int(cx + G * ASPECT) + 2):
                u, v = (x - cx) / ASPECT / G, (y - cy) / tilt / G
                r = math.hypot(u, v)
                if r > 1:
                    continue
                theta = atan2(v, u)
                arm = 0.5 + 0.5 * cos(2 * (theta - rot) - 6 * log(r + 0.08))
                clump = sample(tex, (theta - rot) / TAU, r * 1.5)
                core = exp(-r * r * 40)
                dens = core * 1.2 + 1.4 * arm ** 3 * (1 - r) ** 1.2 * (0.4 + clump) + 0.05 * (1 - r)
                if dens < 0.06:
                    continue
                col = lerp((110, 150, 255), (255, 225, 180), min(1.0, core * 1.5 + 0.1))
                if arm > 0.8 and clump > 0.72:        # pink star-forming knots
                    col = (255, 120, 200)
                d = min(1.0, dens)
                cv.put(x, y, shade_char(d), scale(col, 0.35 + 0.75 * d))
                cv.add_bg(x, y, scale(col, 0.22 * d))


# ---------------------------------------------------------------- 6. sun

class Sun:
    name = "Solar Flare"

    def __init__(self):
        self.stars = Stars(120, brightness=0.6)
        self.flares = [(random.uniform(0, TAU), random.uniform(0.4, 1.4)) for _ in range(3)]

    def draw(self, cv, t):
        space_gradient(cv, (4, 1, 4), (8, 2, 4))
        self.stars.draw(cv, t)
        cx, cy, half = layout(cv)
        R = max(2.5, min(half * 0.72, cv.w / ASPECT * 0.2))
        tex = noise_texture(seed=11, cells=10, octaves=4)
        spin = t * 0.04
        pulse = 0.85 + 0.15 * math.sin(t * 0.9)
        sqrt, atan2, asin = math.sqrt, math.atan2, math.asin

        cv.glow(cx, cy, (255, 90, 20), R * 2.6, 0.3 * pulse)
        reach = 2.4
        for y in range(int(cy - R * reach) - 1, int(cy + R * reach) + 2):
            for x in range(int(cx - R * reach * ASPECT) - 1, int(cx + R * reach * ASPECT) + 2):
                u, v = (x - cx) / ASPECT / R, (y - cy) / R
                d2 = u * u + v * v
                if d2 < 1:
                    pz = sqrt(1 - d2)
                    lon = atan2(u, pz) + spin
                    lat = asin(max(-1.0, min(1.0, v)))
                    g = sample(tex, lon / TAU * 2, lat / math.pi + 0.5 + t * 0.01)
                    boil = 0.5 + 0.5 * math.sin(g * 20 - t * 2)
                    heat = (0.55 + 0.3 * g + 0.15 * boil) * (0.62 + 0.38 * pz ** 0.5)
                    col = ramp(HEAT, heat)
                    cv.put(x, y, shade_char(heat), col)
                    cv.set_bg(x, y, scale(col, 0.55))
                else:
                    d = sqrt(d2)
                    if d > reach:
                        continue
                    ang = atan2(v, u)
                    streak = sample(tex, ang / TAU, t * 0.015)
                    glow = math.exp(-(d - 1) * 2.4) * (0.35 + 1.1 * streak ** 2) * pulse
                    cv.add_bg(x, y, scale((255, 120, 40), 0.55 * glow))
                    if glow > 0.5 and (x + y + int(t * 8)) % 3 == 0:
                        cv.put(x, y, ".", (255, 190, 120))

        # flares: glowing loops that rise and fall on the edge
        for i, (a0, sp) in enumerate(self.flares):
            a = a0 + t * 0.03
            h = 0.25 + 0.35 * max(0.0, math.sin(t * sp * 0.5 + i * 2.1))
            for k in range(25):
                s = k / 24
                ang = a + (s - 0.5) * 0.5
                rad = 1.0 + h * math.sin(s * math.pi)
                px = cx + math.cos(ang) * rad * R * ASPECT
                py = cy + math.sin(ang) * rad * R
                cv.put(px, py, "*" if k % 4 == 0 else "~", ramp(HEAT, 0.6 + 0.3 * math.sin(s * 3)))
                if k % 3 == 0:
                    cv.glow(px, py, (255, 120, 40), 1.5, 0.3)


# ---------------------------------------------------------------- 7. low orbit

class Orbit:
    name = "Low Orbit"
    SUN = (0.86, -0.12, 0.3)   # sunlight comes from the right, so the left is night

    def __init__(self):
        self.stars = Stars(120, brightness=0.8)

    def draw(self, cv, t):
        space_gradient(cv, (1, 1, 8), (3, 4, 16))
        self.stars.draw(cv, t)
        w, h = cv.w, cv.h
        R = w / ASPECT * 0.55                # Earth is huge: we only see the top of it
        ex, ey = w / 2, h * 0.64 + R
        land = noise_texture(seed=5, cells=6, octaves=5)
        cloud = noise_texture(seed=9, cells=8, octaves=4)
        Lx, Ly, Lz = self.SUN
        sqrt, exp, sin = math.sqrt, math.exp, math.sin

        for y in range(max(0, int(h * 0.64) - 7), h):
            for x in range(w):
                u, v = (x - ex) / ASPECT / R, (y - ey) / R
                d2 = u * u + v * v
                if d2 >= 1:
                    # above the surface: atmosphere glow and aurora
                    d = sqrt(d2)
                    alt = (d - 1) * R                       # height in rows
                    if alt > 6:
                        continue
                    lit = (u * Lx + v * Ly) / d
                    sky = exp(-alt * 1.5) * (0.15 + max(0.0, lit + 0.3))
                    dawn = exp(-(lit * 5) ** 2) * exp(-alt * 1.2)   # sunrise at the terminator
                    cv.add_bg(x, y, (60 * sky + 255 * dawn, 120 * sky + 120 * dawn,
                                     255 * sky + 40 * dawn))
                    if lit < -0.05 and 0.2 < alt < 5.5:       # aurora on the night side
                        curtain = (0.5 + 0.5 * sin(x * 0.23 + t * 0.7
                                                   + 3 * sin(x * 0.04 - t * 0.25))) ** 3
                        fade = min(1.0, (-lit - 0.05) * 4)
                        a = curtain * fade * exp(-(alt - 0.6) * 0.55)
                        col = lerp((60, 255, 150), (190, 80, 255), min(1.0, alt / 5))
                        cv.add_bg(x, y, scale(col, 0.55 * a))
                        if a > 0.35:
                            cv.put(x, y, "|" if a > 0.6 else "'", scale(col, 0.6 + 0.6 * a))
                    continue
                # the surface
                nz = sqrt(1 - d2)
                lit = u * Lx + v * Ly + nz * Lz
                tu, tv = u * 3.2 + t * 0.004, nz * 3.2
                ground = sample(land, tu, tv)
                cl = sample(cloud, tu * 1.3 + t * 0.002, tv * 1.3)
                haze = (1 - nz) ** 6                          # blue haze near the edge
                if lit > 0:
                    if ground > 0.55:
                        col = lerp((50, 100, 45), (170, 140, 90), min(1.0, (ground - 0.55) * 4))
                    else:
                        col = lerp((5, 25, 80), (20, 70, 150), ground / 0.55)
                    if cl > 0.58:
                        col = lerp(col, (235, 240, 250), min(1.0, (cl - 0.58) * 4))
                    col = lerp(scale(col, min(1.0, lit * 1.6)), (90, 150, 255), haze * 0.7)
                    cv.set_bg(x, y, scale(col, 0.8))
                    if cl > 0.62:
                        cv.put(x, y, "@" if cl > 0.75 else "%", scale(col, 1.15))
                    elif ground > 0.55:
                        cv.put(x, y, ":" if ground < 0.65 else "#", scale(col, 1.4))
                    else:
                        cv.put(x, y, "~" if (x + y) % 4 == 0 else " ", scale(col, 1.5))
                else:
                    cv.set_bg(x, y, lerp((2, 4, 12), (20, 40, 110), haze * 0.6))
                    city = sample(cloud, u * 11, nz * 11)
                    if ground > 0.53 and city > 0.6 and cl < 0.62:
                        b = min(1.0, (city - 0.6) * 5) * min(1.0, -lit * 5)
                        cv.put(x, y, "*" if b > 0.6 else ".", scale((255, 190, 100), 0.5 + 0.5 * b))
                        cv.add_bg(x, y, scale((255, 140, 50), 0.25 * b))

        self._starlink(cv, t)
        self._satellite(cv, t)

    @staticmethod
    def _starlink(cv, t):
        """Every so often a line of satellites drifts across the sky."""
        p = (t % 50) / 26
        if p > 1:
            return
        fade = math.sin(p * math.pi)
        hx, hy = -10 + p * (cv.w + 40), cv.h * 0.12 + p * cv.h * 0.3
        for k in range(14):
            cv.put(hx - k * 3.2, hy - k * 0.35, ".", scale((230, 235, 255), fade * (1 - k / 20)))

    @staticmethod
    def _satellite(cv, t):
        p = (t % 80) / 80
        x = -16 + p * (cv.w + 32)
        y = cv.h * 0.42 - math.sin(p * math.pi) * cv.h * 0.12
        flare = math.exp(-((p - 0.55) * 28) ** 2)          # sun glinting off the panels
        if flare > 0.02:
            cv.glow(x + 6, y, (255, 255, 240), 4, 0.8 * flare)
        body = "|####|=[o]=|####|"
        for i, ch in enumerate(body):
            if ch == "#":
                shine = 0.55 + 0.45 * math.sin(t * 2.5 - i * 0.5)
                col = lerp(scale((70, 110, 240), shine), (255, 255, 255), flare)
            elif ch in "[o]":
                col = (230, 230, 240)
            else:
                col = (150, 150, 165)
            cv.put(x - 8 + i, y, ch, col)
        cv.put(x, y - 1, "|", (150, 150, 165))
        if int(t * 1.5) % 2:
            cv.put(x, y - 2, "*", (255, 70, 70))
            cv.glow(x, y - 2, (255, 50, 50), 1.5, 0.5)
        else:
            cv.put(x, y - 2, ".", (120, 60, 60))


# ---------------------------------------------------------------- 8. pulsar

class Pulsar:
    name = "Pulsar"

    def __init__(self):
        self.stars = Stars(150, brightness=0.8)
        self.sparks = []   # [x, y, dx, dy, life]

    def draw(self, cv, t):
        space_gradient(cv, (1, 1, 8), (3, 1, 10))
        self.stars.draw(cv, t)
        cx, cy, half = layout(cv)
        a = t * 1.3 + 0.3 * math.sin(t * 0.2)        # where the beams point
        flash = math.exp(-(((a % math.pi) - math.pi / 2) * 5) ** 2)  # beam sweeps past us
        tex = noise_texture(seed=13, cells=6, octaves=3)
        reach = max(cv.w / ASPECT, cv.h)
        pi, exp, atan2, hypot = math.pi, math.exp, math.atan2, math.hypot

        for y in range(cv.h):
            for x in range(cv.w):
                u, v = (x - cx) / ASPECT, y - cy
                r = hypot(u, v) + 1e-6
                phi = atan2(v, u)
                diff = (phi - a + pi / 2) % pi - pi / 2     # angle to the nearest beam
                if diff > 0.25:
                    beam = 0.0
                else:
                    width = 0.04 + 1.2 / (r + 3)
                    beam = exp(-(diff / width) ** 2)
                    if diff < 0:
                        beam += exp(diff * 4) * 0.3          # afterglow behind the sweep
                    beam *= exp(-r / (reach * 0.55))
                # a faint ring of gas the pulsar lights up as it sweeps past
                ring = hypot(u, v / 0.42) / (half * 1.7)
                gas = exp(-((ring - 1) * 5) ** 2) * (0.3 + 0.7 * sample(tex, phi / TAU, ring))
                gas *= 0.25 + 1.5 * beam
                if beam > 0.02 or gas > 0.03:
                    cv.add_bg(x, y, (80 * beam + 140 * gas, 160 * beam + 50 * gas,
                                     255 * beam + 170 * gas))
                    if beam > 0.55 and r > 2.5 and (x * 7 + y * 3 + int(t * 20)) % 5 == 0:
                        cv.put(x, y, ".", (190, 230, 255))

        # magnetic field lines, turning with the beams
        for L in (2.5, 4.5, 7.0):
            for k in range(1, 40):
                th = k / 40 * pi
                r = L * math.sin(th) ** 2
                for side in (1, -1):
                    px, py = r * math.cos(th), side * r * math.sin(th)
                    X = px * math.cos(a) - py * math.sin(a)
                    Y = px * math.sin(a) + py * math.cos(a)
                    cv.put(cx + X * ASPECT, cy + Y, ".", (120, 100, 230))

        # particles flung out along the beams
        for direction in (a, a + pi):
            sp = random.uniform(1.0, 2.0)
            self.sparks.append([cx, cy, math.cos(direction) * sp * ASPECT,
                                math.sin(direction) * sp, 25])
        for s in self.sparks:
            s[0] += s[2]
            s[1] += s[3]
            s[4] -= 1
            cv.put(s[0], s[1], "+" if s[4] > 18 else ".", scale((170, 220, 255), s[4] / 25))
        self.sparks = [s for s in self.sparks if s[4] > 0]

        cv.glow(cx, cy, (110, 90, 255), 7, 0.35 + 0.4 * flash)
        cv.glow(cx, cy, (210, 235, 255), 2.5, 0.8 + 0.6 * flash)
        cv.put(cx, cy, "@", (255, 255, 255))
        if flash > 0.3:
            for k in range(1, 6):
                c = scale((200, 230, 255), flash * (1 - k / 6))
                cv.put(cx + k * 2, cy, "-", c)
                cv.put(cx - k * 2, cy, "-", c)


# ---------------------------------------------------------------- 9. comet

class Comet:
    name = "Comet"

    def __init__(self):
        self.stars = Stars(150, meteors=0.02)
        self.dust = []   # [x, y, dx, dy, life]

    def draw(self, cv, t):
        space_gradient(cv, (1, 2, 10), (5, 3, 15))
        self.stars.draw(cv, t)
        cx, cy, half = layout(cv)
        hx = cv.w * 0.27 + math.sin(t * 0.1) * 3
        hy = cy + half * 0.3 + math.sin(t * 0.13)
        ang = -0.28                                      # tails point up and to the right
        dx, dy = math.cos(ang), math.sin(ang)
        length = cv.w / ASPECT
        tex = noise_texture(seed=17, cells=5, octaves=4)
        exp = math.exp

        for y in range(cv.h):
            for x in range(max(0, int(hx - 6 * ASPECT)), cv.w):
                X, Y = (x - hx) / ASPECT, y - hy
                s = X * dx + Y * dy           # distance along the tail
                p = -X * dy + Y * dx          # distance to the side (positive = down)
                if s < -2:
                    continue
                sp = max(s, 0.0)
                wi = 0.3 + 0.04 * sp
                ion = exp(-(p / wi) ** 2) * exp(-sp / (length * 0.5))
                ion *= 0.45 + 0.55 * sample(tex, sp * 0.015 - t * 0.06, p * 0.1 + 0.5)
                pd = p - 0.011 * sp * sp      # the dust tail curves away
                wd = 0.5 + 0.13 * sp
                dust = exp(-(pd / wd) ** 2) * exp(-sp / (length * 0.32)) * 0.85
                if s < 0:
                    ion *= exp(s * 2)
                    dust *= exp(s * 2)
                if ion + dust < 0.03:
                    continue
                cv.add_bg(x, y, (70 * ion + 255 * dust * 0.8, 150 * ion + 215 * dust * 0.8,
                                 255 * ion + 160 * dust * 0.8))
                if ion > 0.45:
                    cv.put(x, y, "-" if ion < 0.8 else "=", scale((170, 215, 255), 0.6 + 0.5 * ion))
                elif dust > 0.4:
                    cv.put(x, y, ":" if dust > 0.65 else ".", scale((255, 230, 190), 0.6 + 0.5 * dust))

        # glittering dust drifting off the head
        if random.random() < 0.6:
            a = ang + random.uniform(0.05, 0.45)
            sp = random.uniform(0.3, 0.8)
            self.dust.append([hx, hy, math.cos(a) * sp * ASPECT, math.sin(a) * sp, 70])
        for d in self.dust:
            d[0] += d[2]
            d[1] += d[3]
            d[3] += 0.004                    # curves away like the dust tail
            d[4] -= 1
            tw = 0.5 + 0.5 * math.sin(d[4] * 0.7)
            cv.put(d[0], d[1], "*" if tw > 0.85 else ".", scale((255, 235, 200), d[4] / 70 * (0.4 + 0.6 * tw)))
        self.dust = [d for d in self.dust if d[4] > 0]

        cv.glow(hx, hy, (90, 255, 170), 4, 0.6)          # comets glow green
        cv.glow(hx, hy, (255, 255, 255), 1.5, 0.9)
        cv.put(hx, hy, "@", (255, 255, 255))


# ---------------------------------------------------------------- 10. northern lights

class NorthernLights:
    name = "Northern Lights"
    # curtains: (base height 0-1, wave size, waves across, speed, height, brightness)
    CURTAINS = [(0.50, 0.07, 1.1, 0.07, 0.30, 1.0),
                (0.36, 0.05, 1.7, -0.05, 0.22, 0.7),
                (0.60, 0.04, 2.4, 0.09, 0.16, 0.55)]

    def __init__(self):
        self.stars = Stars(150, brightness=0.85, meteors=0.008)
        self.size = None

    def _prepare(self, w, h):
        """Mountain shapes, worked out once per screen size."""
        self.horizon = hz = int(h * 0.72)
        rnd = random.Random(4)
        ph = [rnd.uniform(0, TAU) for _ in range(6)]
        self.far, self.near, self.trees = [], [], {}
        for x in range(w):
            u = x / max(1, w)
            peaks = (0.55 * (1 - abs(math.sin(u * 4.1 + ph[0])))
                     + 0.3 * (1 - abs(math.sin(u * 9.7 + ph[1])))
                     + 0.15 * (1 - abs(math.sin(u * 23 + ph[2]))))
            self.far.append(hz - (h * 0.04 + h * 0.3 * peaks ** 1.4))
            hills = 0.5 + 0.3 * math.sin(u * 6 + ph[3]) + 0.2 * math.sin(u * 15 + ph[4])
            self.near.append(hz - 1 - h * 0.05 * hills)
        x = rnd.randint(0, 3)
        while x < w:                      # a ragged line of pine trees
            self.trees[x] = rnd.choice((1, 2, 2, 3))
            x += rnd.choice((1, 2, 2, 3, 5))
        self.size = (w, h)

    def draw(self, cv, t):
        w, h = cv.w, cv.h
        if self.size != (w, h):
            self._prepare(w, h)
        hz = self.horizon
        space_gradient(cv, (1, 3, 14), (6, 16, 34))
        self.stars.draw(cv, t)
        tex = noise_texture(seed=29, cells=9, octaves=3)
        br, bg, bb, chs, fgs = cv.br, cv.bg, cv.bb, cv.ch, cv.fg
        exp, sin = math.exp, math.sin
        GREEN, TEAL, PURPLE, PINK = (40, 255, 130), (40, 210, 200), (170, 70, 255), (255, 70, 150)

        # the aurora: wavy curtains with bright bottom edges and rays going up
        for c, (base, amp, waves, speed, height, power) in enumerate(self.CURTAINS):
            H = h * height
            for x in range(w):
                u = x / w
                yb = h * (base + amp * sin(u * waves * TAU + t * speed * 5
                                           + 1.5 * sin(u * 3 + t * speed * 3 + c)))
                ray = sample(tex, u * 5 + c * 0.3 + t * 0.004, t * 0.01 + c * 0.37)
                fold = 0.5 + 0.5 * sin(u * 11 + t * speed * 9 + c * 2)
                strength = power * (0.25 + 0.75 * fold) * (0.35 + 1.1 * ray ** 2)
                if strength < 0.05:
                    continue
                top = max(0, int(yb - H * 2.6))
                for y in range(top, min(hz, int(yb) + 3)):
                    dy = yb - y                       # rows above the bottom edge
                    if dy >= 0:
                        a = exp(-dy / H) * min(1.0, 0.35 + dy * 0.9)
                        col = (lerp(GREEN, TEAL, dy / H) if dy < H
                               else lerp(TEAL, PURPLE, min(1.0, (dy - H) / H)))
                    else:
                        a = exp(dy * 1.6) * 0.3 * strength   # faint pink fringe below
                        col = PINK
                    a *= strength
                    if a < 0.03:
                        continue
                    i = y * w + x
                    br[i] += col[0] * a * 0.55
                    bg[i] += col[1] * a * 0.55
                    bb[i] += col[2] * a * 0.55
                    if a > 0.36 and ray > 0.58 and dy > 0:
                        chs[i] = "|" if a > 0.55 else "'"
                        k = 0.55 + 0.6 * a
                        fgs[i] = (min(255, int(col[0] * k)) << 16 | min(255, int(col[1] * k)) << 8
                                  | min(255, int(col[2] * k)))

        # far mountains: blue-grey, snow on the peaks, lit faintly by the sky
        top_of_range = min(self.far)
        for x in range(w):
            ridge = self.far[x]
            tall = (hz - ridge) / max(1.0, hz - top_of_range)
            r0 = int(ridge)
            for y in range(max(0, r0), hz):
                depth = (y - ridge) / max(1.0, hz - ridge)
                snow = max(0.0, 1 - (y - ridge) / 2.2) * min(1.0, max(0.0, tall - 0.45) * 3)
                body = lerp((20, 30, 52), (5, 8, 16), max(0.0, depth) ** 0.6)
                col = lerp(body, (125, 165, 175), snow * 0.85)
                i = y * w + x
                br[i], bg[i], bb[i] = col
                chs[i] = " "
            if 0 <= r0 - 1 and ridge - r0 < 0.5:                # smooth the ridge line
                col = lerp((20, 30, 52), (125, 165, 175), min(1.0, max(0.0, tall - 0.45) * 3) * 0.85)
                cv.put(x, r0 - 1, "▄", col)
            # near hills with pine trees, almost black
            near = int(self.near[x])
            for y in range(max(0, near), hz):
                i = y * w + x
                br[i], bg[i], bb[i] = (3, 6, 10)
                chs[i] = " "
            for k in range(1, self.trees.get(x, 0) + 1):
                cv.put(x, near - k, "▲", (6, 14, 16))
            if 0 < near and x not in self.trees:
                cv.put(x, near - 1, "▄", (3, 6, 10))

        # a still lake at the bottom reflecting all of it
        for y in range(hz, h):
            src = 2 * hz - y - 1
            if src < 0:
                break
            depth = (y - hz) / max(1, h - hz)
            for x in range(w):
                wob = int(1.5 * depth * sin(y * 1.9 + t * 1.3 + x * 0.05))
                j = src * w + min(w - 1, max(0, x + wob))
                i = y * w + x
                k = 0.5 - 0.2 * depth
                r, g, b = br[j] * k + 2, bg[j] * k + 4, bb[j] * k + 10
                br[i], bg[i], bb[i] = r, g, b
                lum = r + g + b
                if lum > 70 and (x * 7 + y * 3 + int(t * 3)) % 6 == 0:
                    chs[i] = "~" if (x + y) % 2 else "-"
                    fgs[i] = (min(255, int(r * 1.9)) << 16 | min(255, int(g * 1.9)) << 8
                              | min(255, int(b * 1.9)))
                else:
                    chs[i] = " "


# ---------------------------------------------------------------- 11. eagle nebula

# Glowing gas, from hot and blue near the young stars out to gold and
# magenta far away (roughly the Hubble colors, pushed further).
NEBULA = [(0.0, (190, 250, 255)), (0.12, (70, 215, 220)), (0.27, (40, 140, 215)),
          (0.42, (85, 70, 190)), (0.56, (175, 60, 175)), (0.7, (240, 85, 120)),
          (0.84, (250, 140, 60)), (1.0, (255, 205, 90))]
# The edges of the pillars, where starlight is boiling them away.
RIM = [(0.0, (255, 120, 70)), (0.3, (255, 190, 90)), (0.55, (255, 240, 200)),
       (0.75, (255, 140, 200)), (1.0, (140, 230, 255))]


class EagleNebula:
    """The Pillars of Creation: three towers of cold dust and gas, lit from
    above by a cluster of young stars that is slowly blowing them away."""
    name = "Eagle Nebula"
    # (x, top, base radius, top radius, lean, head size, wiggle phase): sizes
    # are fractions of the screen height, x is a fraction of the width
    PILLARS = [(0.20, 0.13, 0.21, 0.075, 0.10, 0.045, 0.3),
               (0.52, 0.40, 0.15, 0.06, -0.03, 0.035, 2.1),
               (0.80, 0.60, 0.10, 0.045, 0.06, 0.025, 4.0)]

    def __init__(self):
        self.stars = Stars(120, brightness=0.7, meteors=0.006)
        self.size = None
        self.streamers = []   # gas boiling off the pillar edges [x, y, dx, dy, life, max, hue]
        self.sparkles = []    # [x, y, life, color]

    # -------------------------------------------------------- set up per size

    def _prepare(self, w, h):
        self.size = (w, h)
        n = w * h
        rough = noise_texture(seed=23, cells=10, octaves=4)
        gas = noise_texture(seed=21, cells=5, octaves=5)
        hue = noise_texture(seed=22, cells=4, octaves=3)
        self.light = lx, ly = w * 0.66, -h * 0.12          # the young star cluster

        # each pillar is a chain of soft circles running up a wavy centre line
        F = [0.0] * n
        heads = []
        for x0, top, rb, rt, lean, head, ph in self.PILLARS:
            bx, by, ty = x0 * w / ASPECT, h + 3.0, top * h
            for k in range(81):
                s = k / 80
                cy = by + (ty - by) * s
                cx = bx + lean * h * s + 0.025 * h * math.sin(s * 6 + ph)
                r = (rb + (rt - rb) * s ** 0.7) * h + head * h * math.exp(-((s - 0.92) / 0.06) ** 2)
                r = max(1.0, r)
                for y in range(max(0, int(cy - r)), min(h, int(cy + r) + 2)):
                    for x in range(max(0, int((cx - r) * ASPECT)), min(w, int((cx + r) * ASPECT) + 2)):
                        f = 1 - math.hypot(x / ASPECT - cx, y - cy) / r
                        i = y * w + x
                        if f > F[i]:
                            F[i] = f
            heads.append((cx * ASPECT, cy, r))

        # ragged edges, then how solid each cell is
        A = [0.0] * n
        for y in range(h):
            for x in range(w):
                i = y * w + x
                if F[i] <= 0:
                    continue
                edge = min(1.0, F[i] * 5)                 # only roughen near the pillars
                v = (F[i] * 2.6 + edge * ((sample(rough, x / w * 4, y / h * 3) - 0.5) * 1.5
                     + (sample(gas, x / w * 9, y / h * 6) - 0.5) * 0.6) - 0.35)
                A[i] = 0.0 if v <= 0 else 1.0 if v >= 1 else v * v * (3 - 2 * v)

        def a_at(x, y):
            if 0 <= x < w and 0 <= y < h:
                return A[y * w + x]
            return 0.0

        # rims face the light (up and to the right); a halo spills off them
        rim = [0.0] * n
        for y in range(h):
            for x in range(w):
                a = A[y * w + x]
                if a > 0.05:
                    toward = (a_at(x + 1, y - 1) + a_at(x, y - 1) + a_at(x + 2, y - 2) + a_at(x + 3, y - 1)) / 4
                    rim[y * w + x] = min(1.0, a * (1 - toward) * 1.8)
        halo = [0.0] * n
        for y in range(h):
            for x in range(w):
                r = rim[y * w + x]
                if r > 0.15:
                    for dy in range(-2, 2):
                        for dx in range(-3, 4):
                            xx, yy = x + dx, y + dy
                            if 0 <= xx < w and 0 <= yy < h:
                                k = r * (1 - abs(dx) / 4) * (1 - abs(dy + 0.5) / 2.5) * 0.35
                                j = yy * w + xx
                                if k > halo[j]:
                                    halo[j] = k

        # the gas: color by distance from the stars, wobbled by noise
        self.cells = cells = []
        for y in range(h):
            for x in range(w):
                i = y * w + x
                u, v = x / w, y / h
                d = math.hypot((x - lx) / ASPECT, y - ly) / h
                hv = sample(hue, u * 1.3, v * 1.1)
                g = sample(gas, u * 1.6, v * 1.4)
                p = max(0.0, min(1.0, 0.05 + d * 0.62 + (hv - 0.5) * 0.7))
                ca = ramp(NEBULA, p)
                cb = ramp(NEBULA, min(1.0, p + 0.2 + 0.15 * hv))     # the color it drifts toward
                bright = (0.12 + 0.95 * g ** 1.6) * (1.25 - 0.55 * min(1.0, d))
                tex = sample(rough, u * 7, v * 5)
                body = lerp((26, 10, 12), (105, 48, 30), tex * 0.8 + 0.2 * (1 - v))
                rc = ramp(RIM, sample(hue, u * 3 + 0.4, v * 2))
                cells.append((x, y, u, v, d, ca, cb, bright, hv * TAU, A[i], rim[i], halo[i],
                              body, rc, tex))

        # protostars glowing inside the pillar heads, and where gas boils off
        self.protostars = [(hx - rr * 0.15 * ASPECT, hy + rr * 0.9, k) for k, (hx, hy, rr) in enumerate(heads)]
        self.tips = heads
        self.jet = heads[0]
        self.rims = [(x, y) for y in range(h) for x in range(w)
                     if rim[y * w + x] > 0.5 and y < h * 0.85]
        rnd = random.Random(7)
        self.bright_stars = []
        for _ in range(max(6, w // 14)):
            x, y = rnd.uniform(0, w), rnd.uniform(0, h * 0.9)
            if A[int(y) * w + int(x)] < 0.1:
                self.bright_stars.append((x, y, rnd.uniform(0.5, 1.0), rnd.uniform(0, TAU),
                                          rnd.choice(((200, 225, 255), (255, 240, 220), (255, 200, 150),
                                                      (170, 200, 255), (255, 170, 210)))))

    # -------------------------------------------------------- every frame

    def draw(self, cv, t):
        w, h = cv.w, cv.h
        if self.size != (w, h):
            self._prepare(w, h)
            self.streamers, self.sparkles = [], []
        space_gradient(cv, (2, 2, 10), (5, 2, 12))
        drift = noise_texture(seed=24, cells=6, octaves=3)
        shim = noise_texture(seed=25, cells=12, octaves=3)
        sin, exp = math.sin, math.exp
        lx, ly = self.light
        wave_r = (t % 16) / 16 * 2.2                       # a ring of light rolling out from the stars
        ox, oy = t * 0.006, t * 0.0025
        sx, sy = -t * 0.02, t * 0.008
        br, bg, bb, chs, fgs = cv.br, cv.bg, cv.bb, cv.ch, cv.fg
        RAMPC = " .·:-=+*"
        for (x, y, u, v, d, ca, cb, bright, ph, a, rim, halo, body, rc, tex) in self.cells:
            i = y * w + x
            m = drift[int((v * 1.3 + oy) * 96) % 96][int((u * 1.3 + ox) * 192) % 192]
            k = 0.5 + 0.5 * sin(t * 0.12 + ph)
            wave = exp(-((d - wave_r) / 0.07) ** 2)
            gb = bright * (0.45 + 1.1 * m) + 0.35 * wave * bright
            r = (ca[0] + (cb[0] - ca[0]) * k) * gb
            g = (ca[1] + (cb[1] - ca[1]) * k) * gb
            b = (ca[2] + (cb[2] - ca[2]) * k) * gb
            if a > 0.01:                                   # a pillar in front of the gas
                s = shim[int((v * 4 + sy) * 96) % 96][int((u * 4 + sx) * 192) % 192]
                glow = rim * (0.55 + 0.9 * s) + 0.6 * wave * rim
                r = r * (1 - a) * 0.5 + body[0] * a + rc[0] * glow
                g = g * (1 - a) * 0.5 + body[1] * a + rc[1] * glow
                b = b * (1 - a) * 0.5 + body[2] * a + rc[2] * glow
                br[i], bg[i], bb[i] = r * 0.8, g * 0.8, b * 0.8
                if glow > 0.35:
                    chs[i] = "▓" if glow > 0.8 else "▒"
                    fgs[i] = pack((min(255, rc[0] * glow * 1.25 + 40), min(255, rc[1] * glow * 1.25 + 30),
                                   min(255, rc[2] * glow * 1.25 + 30)))
                elif a > 0.5:
                    chs[i] = "░" if tex > 0.45 else "▒" if tex > 0.3 else " "
                    fgs[i] = pack((body[0] * 1.6 + 10, body[1] * 1.6 + 6, body[2] * 1.6 + 6))
                continue
            if halo > 0.01:                                 # light spilling off the rims
                s = shim[int((v * 4 + sy) * 96) % 96][int((u * 4 + sx) * 192) % 192]
                hk = halo * (0.6 + 0.8 * s)
                r, g, b = r + rc[0] * hk, g + rc[1] * hk, b + rc[2] * hk
            br[i], bg[i], bb[i] = r * 0.42, g * 0.42, b * 0.42
            lvl = int(gb * 0.75 * len(RAMPC))
            if lvl > 1:
                chs[i] = RAMPC[min(len(RAMPC) - 1, lvl)]
                fgs[i] = pack((min(255, r * 0.75), min(255, g * 0.75), min(255, b * 0.75)))

        self.stars.draw(cv, t)
        cv.glow(lx, ly, (180, 230, 255), h * 0.55, 0.25)    # glare from the cluster
        cv.glow(lx, ly, (255, 255, 255), h * 0.2, 0.4)
        for k, (hx, hy, rr) in enumerate(self.tips):         # the pillar tips blaze brightest
            p = 0.75 + 0.25 * math.sin(t * 0.7 + k * 1.9)
            cv.glow(hx + rr * 0.4 * ASPECT, hy - rr * 0.6, (255, 210, 150), rr * 1.3, 0.3 * p)
            cv.glow(hx + rr * 0.4 * ASPECT, hy - rr * 0.6, (255, 140, 210), rr * 2.4, 0.12 * p)
        self._bright_stars(cv, t)
        self._protostars(cv, t)
        self._streamers(cv, t)
        self._sparkles(cv)

    def _bright_stars(self, cv, t):
        """Big stars with long diffraction spikes that pulse gently."""
        for x, y, mag, ph, col in self.bright_stars:
            tw = 0.75 + 0.25 * math.sin(t * 1.7 + ph)
            L = int((3 + 7 * mag) * tw)
            for k in range(1, L + 1):
                f = (1 - k / (L + 1)) ** 1.5 * mag * tw
                c = scale(col, f)
                cv.put(x - k, y, "─", c)
                cv.put(x + k, y, "─", c)
                if k <= L // 2:
                    cv.put(x, y - k, "│", c)
                    cv.put(x, y + k, "│", c)
                if mag > 0.8 and k <= L // 3:
                    cv.put(x + k * 1.2, y - k * 0.6, "╱", scale(c, 0.6))
                    cv.put(x - k * 1.2, y + k * 0.6, "╱", scale(c, 0.6))
                    cv.put(x + k * 1.2, y + k * 0.6, "╲", scale(c, 0.6))
                    cv.put(x - k * 1.2, y - k * 0.6, "╲", scale(c, 0.6))
            cv.put(x, y, "✦", lerp(col, (255, 255, 255), 0.6))
            cv.glow(x, y, col, 1.5 + 2.5 * mag, 0.55 * tw * mag)

    def _protostars(self, cv, t):
        """Baby stars hidden in the pillar heads, and a jet from one of them."""
        for x, y, k in self.protostars:
            p = 0.6 + 0.4 * math.sin(t * (0.9 + 0.3 * k) + k * 2)
            cv.glow(x, y, (255, 30, 40), 2.8, 0.6 * p)
            cv.glow(x, y, (255, 120, 60), 1, 0.4 * p)
            cv.put(x, y, "*", lerp((255, 90, 70), (255, 220, 180), p))
        x, y, k = self.protostars[0]                       # a Herbig-Haro jet, both ways
        ang = -0.5
        for side in (-1, 1):
            for j in range(1, 13):
                q = (t * 0.6 - j / 12) % 1.0
                knot = math.exp(-((q - 0.5) / 0.12) ** 2)
                c = lerp((160, 60, 255), (120, 255, 255), j / 12)
                px = x + side * math.cos(ang) * j * 1.6
                py = y + side * math.sin(ang) * j * 0.8
                cv.put(px, py, "•" if knot > 0.6 else "·", scale(c, 0.35 + 0.65 * knot))
                if knot > 0.6:
                    cv.glow(px, py, c, 1.2, 0.35 * knot)

    def _streamers(self, cv, t):
        """Gas boiling off the lit edges of the pillars and drifting away."""
        if self.rims and len(self.streamers) < 140:
            for _ in range(3):
                x, y = random.choice(self.rims)
                life = random.randint(30, 80)
                self.streamers.append([x, y, random.uniform(0.02, 0.15), random.uniform(-0.18, -0.08),
                                       life, life, random.random()])
        for s in self.streamers:
            s[0] += s[2]
            s[1] += s[3]
            s[4] -= 1
            f = s[4] / s[5]
            c = lerp(ramp(RIM, s[6]), (120, 220, 255), 1 - f)
            fade = math.sin(f * math.pi)
            cv.put(s[0], s[1], "˙" if f < 0.4 else "·" if f < 0.8 else "•", scale(c, fade))
            cv.add_bg(int(s[0] + 0.5), int(s[1] + 0.5), scale(c, 0.15 * fade))
        self.streamers = [s for s in self.streamers if s[4] > 0]

    def _sparkles(self, cv):
        """Now and then a new star flickers into view somewhere in the gas."""
        if random.random() < 0.05:
            self.sparkles.append([random.uniform(0, cv.w), random.uniform(0, cv.h), 24,
                                  random.choice(((150, 230, 255), (255, 160, 220), (255, 230, 150),
                                                 (180, 255, 200)))])
        for s in self.sparkles:
            s[2] -= 1
            f = math.sin(s[2] / 24 * math.pi)
            cv.put(s[0], s[1], "✦" if f > 0.6 else "+" if f > 0.3 else "·", scale(s[3], 0.4 + 0.6 * f))
            cv.glow(s[0], s[1], s[3], 1.8, 0.5 * f)
        self.sparkles = [s for s in self.sparkles if s[2] > 0]


SCENES = {
    "planet": RingedPlanet,
    "constellations": Constellations,
    "blackhole": BlackHole,
    "warp": Warp,
    "galaxy": Galaxy,
    "sun": Sun,
    "orbit": Orbit,
    "pulsar": Pulsar,
    "comet": Comet,
    "aurora": NorthernLights,
    "nebula": EagleNebula,
}
