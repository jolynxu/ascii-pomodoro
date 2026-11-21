"""The space backgrounds. Each scene draws itself onto a Canvas every frame.

    planet     a ringed gas giant with a glowing atmosphere and a moon
    nebula     drifting clouds of glowing gas and newborn stars
    blackhole  a black hole with a swirling, glowing accretion disk
    warp       flying through space at warp speed
    galaxy     a slowly turning spiral galaxy
    sun        a boiling star with a corona and solar flares
    orbit      low Earth orbit: city lights, aurora, a satellite, a Starlink train
    pulsar     a spinning neutron star sweeping lighthouse beams
    comet      a comet with a blue ion tail and a curved dust tail
    eclipse    a total solar eclipse with a corona and a diamond ring
"""

import math
import random

from canvas import ASPECT, lerp, ramp, scale

TAU = math.tau
RAMP = " .:-=+*#%@"           # dark -> bright shading characters
LIGHT = (-0.6, -0.5, 0.62)    # light comes from the upper left

HEAT = [(0.0, (40, 4, 0)), (0.3, (200, 50, 10)), (0.55, (255, 140, 30)),
        (0.8, (255, 215, 130)), (1.0, (255, 252, 240))]


def layout(cv):
    """Centre point and half-height of the space below the clock."""
    top = min(12, cv.h * 0.45)
    bottom = cv.h - 2
    return cv.w / 2, (top + bottom) / 2, (bottom - top) / 2


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
    def __init__(self, count=160, brightness=1.0):
        self.brightness = brightness
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
        self.shooting = ShootingStars()

    def draw(self, cv, t):
        space_gradient(cv)
        self.stars.draw(cv, t)
        self.shooting.draw(cv)

        cx, cy, half = layout(cv)
        R = max(2.5, min(half * 0.42, cv.w / ASPECT * 0.1))

        ma = t * 0.4
        moon = (cx + math.cos(ma) * 2.9 * R * ASPECT, cy + math.sin(ma) * 2.9 * R * 0.45,
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


# ---------------------------------------------------------------- 2. nebula

class Nebula:
    name = "Nebula"

    def __init__(self):
        self.stars = Stars(120)
        self.size = None
        rnd = random.Random()
        self.young = [(rnd.uniform(0.1, 0.9), rnd.uniform(0.2, 0.95), rnd.uniform(0, TAU),
                       rnd.choice([(255, 200, 255), (180, 240, 255), (255, 230, 190)]))
                      for _ in range(4)]

    def _prepare(self, w, h):
        """Work out the cloud shapes once per screen size."""
        a_tex = noise_texture(seed=7, cells=5, octaves=5)
        b_tex = noise_texture(seed=21, cells=4, octaves=5)
        self.A, self.B, self.P = [], [], []
        k = 1.1 / w   # texture tiles across the screen width
        for y in range(h):
            for x in range(w):
                u, v = x * k, y * ASPECT * k * 2   # texture is half as tall as wide
                a = sample(a_tex, u, v)
                b = sample(b_tex, u * 0.8 + 0.3, v * 0.8 + 0.5)
                self.A.append(a)
                self.B.append(b)
                self.P.append(a * 11 + b * 7)
        self.size = (w, h)

    def draw(self, cv, t):
        if self.size != (cv.w, cv.h):
            self._prepare(cv.w, cv.h)
        sin = math.sin
        br, bg, bb, chs, fgs = cv.br, cv.bg, cv.bb, cv.ch, cv.fg
        for i, (a, b, p) in enumerate(zip(self.A, self.B, self.P)):
            s = 0.5 + 0.5 * sin(t * 0.7 + p)          # slow shimmering
            m = min(1.0, max(0.0, a - 0.45) * 2.6) * (0.75 + 0.35 * s)        # magenta gas
            c = min(1.0, max(0.0, b - 0.5) * 2.8) * (0.75 + 0.35 * (1 - s))   # teal gas
            ridge = min(1.0, max(0.0, 1 - abs(a - b) * 8) * m * c * 4)  # glow where they meet
            r = 4 + 150 * m * m + 20 * c + 140 * ridge
            g = 2 + 18 * m + 105 * c * c + 100 * ridge
            bl = 14 + 115 * m + 135 * c * c + 80 * ridge
            br[i], bg[i], bb[i] = r, g, bl
            lum = (r + g + bl) / 765
            if lum > 0.2:
                chs[i] = ".:*"[min(2, int((lum - 0.2) * 7))]
                k = 1.6 + 0.4 * s
                fgs[i] = (min(255, int(r * k)) << 16 | min(255, int(g * k)) << 8
                          | min(255, int(bl * k)))
        self.stars.draw(cv, t)

        for x, y, ph, col in self.young:   # newborn stars with light spikes
            px, py = x * cv.w, y * cv.h
            pulse = 0.7 + 0.3 * math.sin(t * 1.3 + ph)
            cv.glow(px, py, col, 4, 0.45 * pulse)
            cv.glow(px, py, (255, 255, 255), 1.5, 0.5 * pulse)
            for k in range(1, 4):
                fade = scale(col, pulse * (1 - k / 4))
                cv.put(px + k * 2, py, "-", fade)
                cv.put(px - k * 2, py, "-", fade)
            cv.put(px, py - 1, "|", scale(col, pulse * 0.7))
            cv.put(px, py + 1, "|", scale(col, pulse * 0.7))
            cv.put(px, py, "*", (255, 255, 255))


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
        R = max(2.0, min(half * 0.42, cv.w / ASPECT * 0.075))  # size of the shadow
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
        G = max(4.0, min(half * 1.05 / tilt, cv.w * 0.44 / ASPECT))  # galaxy radius
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
        R = max(2.5, min(half * 0.55, cv.w / ASPECT * 0.13))
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
        self.stars = Stars(150)
        self.shooting = ShootingStars(0.02)
        self.dust = []   # [x, y, dx, dy, life]

    def draw(self, cv, t):
        space_gradient(cv, (1, 2, 10), (5, 3, 15))
        self.stars.draw(cv, t)
        self.shooting.draw(cv)
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


# ---------------------------------------------------------------- 10. total eclipse

class Eclipse:
    name = "Total Eclipse"

    def __init__(self):
        self.stars = Stars(70, brightness=0.55)

    def draw(self, cv, t):
        space_gradient(cv, (3, 5, 20), (16, 18, 48))      # the sky goes dark blue
        self.stars.draw(cv, t)
        cx, cy, half = layout(cv)
        R = max(2.5, min(half * 0.5, cv.w / ASPECT * 0.11))

        vx, vy = cv.w * 0.8, cv.h * 0.32                  # Venus comes out during totality
        cv.glow(vx, vy, (255, 250, 220), 1.5, 0.4)
        cv.put(vx, vy, "*", (255, 252, 235))

        off = 0.09 * math.sin(t * 0.12) ** 3              # the moon drifts across the sun
        expo = max(0.0, abs(off) - 0.06) / 0.03           # how much sun peeks out (0-1)
        tex = noise_texture(seed=23, cells=7, octaves=4)
        exp, atan2, hypot = math.exp, math.atan2, math.hypot

        reach = 3.3
        for y in range(int(cy - R * reach) - 1, int(cy + R * reach) + 2):
            for x in range(int(cx - R * reach * ASPECT) - 1, int(cx + R * reach * ASPECT) + 2):
                u, v = (x - cx) / ASPECT / R, (y - cy) / R
                if hypot(u - off, v) < 1:                 # the moon
                    cv.set_bg(x, y, (5, 5, 12))
                    cv.put(x, y, " ", (0, 0, 0))
                    continue
                d = hypot(u, v)
                if d > reach:
                    continue
                ang = atan2(v, u)
                rays = (0.5 + 0.5 * math.sin(ang * 11 + 2 * math.sin(ang * 3 + t * 0.05))) ** 2
                streak = 0.55 * sample(tex, ang / TAU * 3, 0.2 + t * 0.003) + 0.45 * rays
                plume = 0.6 + 0.4 * abs(math.cos(ang)) ** 3   # longer streamers at the sides
                corona = (exp(-(d - 1) * 0.85 / plume) * (0.1 + 3.2 * streak ** 2.5)
                          + exp(-(d - 1) * 5) * 0.9) * (1 - 0.45 * expo) * min(1.0, (reach - d) / 1.2)
                col = lerp((110, 140, 255), (255, 250, 245), min(1.0, corona * 0.9))
                cv.add_bg(x, y, scale(col, 0.75 * min(1.3, corona)))
                if corona > 0.35:
                    # streamers drawn with lines pointing away from the sun
                    c, sn = abs(math.cos(ang)), abs(math.sin(ang))
                    ch = "-" if c > 0.92 else "|" if sn > 0.92 else ("\\" if u * v > 0 else "/")
                    if (x * 3 + y * 5) % 4 == 0 or corona > 0.9:
                        cv.put(x, y, ch, scale(col, min(1.0, 0.4 + corona * 0.6)))
                if d < 1.2:                                 # prominences: pink flames
                    prom = sample(tex, ang / TAU * 3, 0.7)
                    if prom > 0.6 and d < 1 + (prom - 0.6) * 1.8:
                        cv.put(x, y, "*" if prom > 0.7 else "~", (255, 90, 140))
                        cv.add_bg(x, y, (110, 20, 50))
                    elif d < 1.07:
                        cv.add_bg(x, y, (90, 15, 45))

        if expo > 0:
            # the diamond ring: one blazing point of sun at the moon's edge
            side = -1 if off > 0 else 1
            bx, by = cx + side * R * ASPECT * 0.98, cy - R * 0.15
            cv.glow(bx, by, (255, 250, 230), R * 1.4, 0.7 * expo)
            cv.glow(bx, by, (255, 255, 255), 1.5, 1.2 * expo)
            n = int(8 * expo)
            for k in range(1, n):
                c = scale((255, 250, 235), expo * (1 - k / n))
                cv.put(bx + k * 2, by, "-", c)
                cv.put(bx - k * 2, by, "-", c)
                if k < n / 2:
                    cv.put(bx, by - k, "|", c)
                    cv.put(bx, by + k, "|", c)
            cv.put(bx, by, "*", (255, 255, 255))
        elif abs(off) > 0.045:
            # Baily's beads: sunlight through valleys on the moon's edge
            side = -1 if off > 0 else 1
            for k, da in enumerate((-0.5, -0.2, 0.15, 0.45)):
                a = (0 if side > 0 else math.pi) + da
                if (int(t * 3) + k) % 3:
                    bx, by = cx + math.cos(a) * R * ASPECT, cy + math.sin(a) * R
                    cv.put(bx, by, "*", (255, 250, 230))
                    cv.glow(bx, by, (255, 240, 210), 1.5, 0.4)


SCENES = {
    "planet": RingedPlanet,
    "nebula": Nebula,
    "blackhole": BlackHole,
    "warp": Warp,
    "galaxy": Galaxy,
    "sun": Sun,
    "orbit": Orbit,
    "pulsar": Pulsar,
    "comet": Comet,
    "eclipse": Eclipse,
}
