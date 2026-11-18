"""The space background: a spinning ringed planet, an orbiting moon,
twinkling stars and the odd shooting star."""

import math
import random

RAMP = ".:-=+*#%@"           # dark -> bright shading characters
LIGHT = (-0.6, -0.5, 0.62)   # light comes from the upper left
ASPECT = 2.2                 # terminal characters are about twice as tall as wide


def put(grid, x, y, ch, color):
    x, y = int(round(x)), int(round(y))
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        grid[y][x] = f"\033[38;5;{color}m{ch}"


class SpaceScene:
    def __init__(self):
        # x, y (0-1), twinkle speed, twinkle phase
        self.stars = [[random.random(), random.random(), random.uniform(1, 4),
                       random.uniform(0, 6.3)] for _ in range(150)]
        self.shooting = []  # [x, y, dx, dy, frames_left]

    def draw(self, grid, t, cx, cy, R):
        rows, cols = len(grid), len(grid[0])
        self._stars(grid, t, cols, rows)
        self._shooting_stars(grid, cols, rows)

        ma = t * 0.4
        moon = (cx + math.cos(ma) * 2.9 * R * ASPECT,
                cy + math.sin(ma) * 2.9 * R * 0.45,
                max(1.2, R * 0.28))
        moon_front = math.sin(ma) > 0

        # back to front, so closer things cover farther ones
        if not moon_front:
            self._moon(grid, *moon)
        self._ring(grid, t, cx, cy, R, front=False)
        self._sphere(grid, cx, cy, R, self._planet_color, t * 0.5)
        self._ring(grid, t, cx, cy, R, front=True)
        if moon_front:
            self._moon(grid, *moon)

    # ---------------------------------------------------------- pieces

    def _stars(self, grid, t, cols, rows):
        for s in self.stars:
            tw = math.sin(t * s[2] + s[3])
            ch = "*" if tw > 0.9 else "+" if tw > 0.5 else "."
            color = 231 if tw > 0.5 else (240, 244, 153)[int(s[3] * 10) % 3]
            put(grid, s[0] * cols, s[1] * rows, ch, color)

    def _shooting_stars(self, grid, cols, rows):
        if random.random() < 0.015:
            self.shooting.append([random.uniform(0, cols * 0.6), random.uniform(0, rows * 0.3),
                                  random.uniform(1.5, 2.5), random.uniform(0.4, 0.8), 40])
        for s in self.shooting:
            s[0] += s[2]
            s[1] += s[3]
            s[4] -= 1
            for k, c in enumerate((231, 195, 153, 111, 67, 61)):
                put(grid, s[0] - s[2] * k * 0.6, s[1] - s[3] * k * 0.6,
                    "*" if k == 0 else ".", c)
        self.shooting = [s for s in self.shooting if s[4] > 0]

    def _sphere(self, grid, cx, cy, r, palette, spin):
        """Draw a shaded ball. palette(lat, lon, brightness) -> color code."""
        for y in range(int(cy - r) - 1, int(cy + r) + 2):
            for x in range(int(cx - r * ASPECT) - 1, int(cx + r * ASPECT) + 2):
                px, py = (x - cx) / (r * ASPECT), (y - cy) / r
                d2 = px * px + py * py
                if d2 > 1:
                    continue
                pz = math.sqrt(1 - d2)
                b = max(0.0, px * LIGHT[0] + py * LIGHT[1] + pz * LIGHT[2])
                ch = RAMP[min(len(RAMP) - 1, int(b * len(RAMP)))]
                put(grid, x, y, ch, palette(py, math.atan2(px, pz) + spin, b))

    @staticmethod
    def _planet_color(lat, lon, b):
        if b < 0.12:
            return 236  # night side
        bands = (94, 130, 136, 172, 179, 180, 215, 222)
        stripe = math.sin(lat * 9 + 0.6 * math.sin(lon * 2 + lat * 4))
        return bands[int((stripe + 1) / 2 * (len(bands) - 1))]

    def _moon(self, grid, mx, my, mr):
        self._sphere(grid, mx, my, mr,
                     lambda lat, lon, b: (238, 242, 246, 250, 254)[min(4, int(b * 5))], 0)

    def _ring(self, grid, t, cx, cy, R, front, tilt=0.35):
        """Draw the half of the ring in front of (or behind) the planet."""
        for y in range(int(cy - 2.2 * R * tilt) - 1, int(cy + 2.2 * R * tilt) + 2):
            for x in range(int(cx - 2.2 * R * ASPECT), int(cx + 2.2 * R * ASPECT) + 1):
                u, v = (x - cx) / ASPECT, (y - cy) / tilt
                r = math.hypot(u, v) / R
                if not 1.35 < r < 2.1 or 1.74 < r < 1.82 or (v > 0) != front:
                    continue  # outside the ring, in the gap, or the other half
                if int(math.atan2(v, u) * 20 - t * 4 + r * 7) % 9 == 0:
                    ch = "."  # ring particles drifting around
                else:
                    ch = ":" if r < 1.55 else "=" if r < 1.74 else "-"
                put(grid, x, y, ch, 223 if r < 1.55 else 180 if r < 1.74 else 144)
