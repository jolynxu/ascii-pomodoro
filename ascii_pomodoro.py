#!/usr/bin/env python3
"""Space-themed pomodoro focus timer for the macOS terminal.

While a focus session is running, apps on the blocklist in config.json are
quit automatically. Spotify (the desktop app) can be controlled from here.

Usage:
    python3 ascii_pomodoro.py                  # uses the times in config.json
    python3 ascii_pomodoro.py --focus 50 --break 10
    python3 ascii_pomodoro.py --focus 0.2 --break 0.1   # quick test (12s / 6s)

    python3 ascii_pomodoro.py --scene nebula   # start on a different background

Keys:
    space  start / pause         s  skip to next session
    r      restart this session  q  quit
    p      Spotify play/pause    n  next song    b  previous song
    left/right or [ ]  change background    1-9, 0  jump to a background
    g      glow on/off           c  true color / 256 color
"""

import argparse
import json
import math
import os
import select
import shutil
import sys
import threading
import time

import mac
from canvas import Canvas, Renderer, lerp, scale, supports_truecolor
from scenes import SCENES

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
FPS = 20

CLEAR, HOME, RESET = "\033[2J", "\033[H", "\033[0m"
HIDE_CURSOR, SHOW_CURSOR = "\033[?25l", "\033[?25h"

PHASES = {                            # label, color
    "focus": ("FOCUS", (110, 195, 255)),
    "short_break": ("SHORT BREAK", (255, 120, 215)),
    "long_break": ("LONG BREAK", (175, 140, 255)),
}
PAUSED = (150, 150, 165)

# Big clock digits: 7 x 10 pixels with rounded corners. Each text row holds
# two pixel rows (drawn with half blocks), so a digit is 7 wide x 5 tall.
FONT = {
    "0": [".#####.", "#######", "##...##", "##...##", "##...##",
          "##...##", "##...##", "##...##", "#######", ".#####."],
    "1": ["..###..", ".####..", "##.##..", "...##..", "...##..",
          "...##..", "...##..", "...##..", "#######", "#######"],
    "2": [".#####.", "#######", "##...##", ".....##", "...####",
          ".####..", "###....", "##.....", "#######", "#######"],
    "3": [".#####.", "#######", ".....##", ".....##", "..####.",
          "..#####", ".....##", "##...##", "#######", ".#####."],
    "4": ["##...##", "##...##", "##...##", "##...##", "#######",
          ".######", ".....##", ".....##", ".....##", ".....##"],
    "5": ["#######", "#######", "##.....", "##.....", "######.",
          "#######", ".....##", "##...##", "#######", ".#####."],
    "6": [".#####.", "#######", "##.....", "##.....", "######.",
          "#######", "##...##", "##...##", "#######", ".#####."],
    "7": ["#######", "#######", ".....##", "....##.", "...##..",
          "..##...", "..##...", "..##...", "..##...", "..##..."],
    "8": [".#####.", "#######", "##...##", "##...##", ".#####.",
          "#######", "##...##", "##...##", "#######", ".#####."],
    "9": [".#####.", "#######", "##...##", "##...##", "#######",
          ".######", ".....##", ".....##", "#######", ".#####."],
    ":": ["..", "..", "##", "##", "..", "..", "##", "##", "..", ".."],
}


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------- timer logic

class Timer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.phase = "focus"
        self.completed = 0          # focus sessions finished
        self.running = False
        self.remaining = self.length()

    def length(self):
        key = {"focus": "focus_minutes", "short_break": "short_break_minutes",
               "long_break": "long_break_minutes"}[self.phase]
        return self.cfg[key] * 60

    def tick(self, dt):
        if not self.running:
            return
        self.remaining -= dt
        if self.remaining <= 0:
            self.finish()

    def finish(self, skipped=False):
        if self.phase == "focus":
            if not skipped:
                self.completed += 1
            every = self.cfg["sessions_before_long_break"]
            long = self.completed > 0 and self.completed % every == 0 and not skipped
            self.phase = "long_break" if long else "short_break"
            self.running = self.cfg["auto_start_breaks"]
            if not skipped:
                mac.notify("Focus session done", "Nice work. Time for a break.")
        else:
            self.phase = "focus"
            self.running = self.cfg["auto_start_focus"]
            if not skipped:
                mac.notify("Break's over", "Ready to focus again?")
        self.remaining = self.length()

    @property
    def blocking(self):
        return self.phase == "focus" and self.running


# ---------------------------------------------------------------- background work

class Watcher(threading.Thread):
    """Checks running apps once a second: quits blocked ones, reads Spotify."""

    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.last_quit = {}
        self.config_mtime = os.path.getmtime(CONFIG_PATH)

    def run(self):
        while True:
            self.reload_blocklist()
            apps = mac.running_apps()
            if apps is not None:
                if self.app.timer.blocking:
                    self.quit_blocked(apps)
                if "spotify" in (a.lower() for a in apps):
                    self.app.spotify = mac.spotify_now_playing()
                else:
                    self.app.spotify = None
            time.sleep(1)

    def reload_blocklist(self):
        """Pick up edits to config.json without restarting."""
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if mtime != self.config_mtime:
                self.config_mtime = mtime
                self.app.timer.cfg["blocklist"] = load_config()["blocklist"]
                self.app.toast("Blocklist reloaded")
        except (OSError, ValueError, KeyError):
            pass  # half-saved or broken file: keep the old list

    def quit_blocked(self, apps):
        blocked = {b.lower() for b in self.app.timer.cfg["blocklist"]}
        for name in apps:
            if name.lower() in blocked:
                # don't spam an app that is showing a "save changes?" dialog
                if time.time() - self.last_quit.get(name, 0) > 10:
                    self.last_quit[name] = time.time()
                    if mac.quit_app(name):
                        self.app.toast(f"Closed {name} - stay focused!")


# ---------------------------------------------------------------- the app

class App:
    def __init__(self, cfg, scene=None, truecolor=True):
        self.timer = Timer(cfg)
        self.scene_names = list(SCENES)
        self.scene_cache = {}
        self.scene_index = 0
        if scene in SCENES:
            self.scene_index = self.scene_names.index(scene)
        self.switched_at = -10.0
        self.glow = True
        self.renderer = Renderer(truecolor)
        self.spotify = None          # (state, track, artist) or None
        self.toasts = []             # (message, expires_at)
        self.now = 0.0

    @property
    def scene(self):
        name = self.scene_names[self.scene_index]
        if name not in self.scene_cache:
            self.scene_cache[name] = SCENES[name]()
        return self.scene_cache[name]

    def toast(self, msg, seconds=4):
        self.toasts.append((msg, time.time() + seconds))

    def set_scene(self, index):
        self.scene_index = index % len(self.scene_names)
        self.switched_at = self.now
        self.toast(f"{self.scene.name}  ({self.scene_index + 1}/{len(self.scene_names)})", 2)

    def handle_key(self, key):
        t = self.timer
        if key == " ":
            t.running = not t.running
        elif key == "s":
            t.finish(skipped=True)
        elif key == "r":
            t.remaining = t.length()
        elif key in ("p", "n", "b"):
            command = {"p": "playpause", "n": "next track", "b": "previous track"}[key]
            threading.Thread(target=mac.spotify_command, args=(command,), daemon=True).start()
        elif key in ("right", "]", "."):
            self.set_scene(self.scene_index + 1)
        elif key in ("left", "[", ","):
            self.set_scene(self.scene_index - 1)
        elif key.isdigit() and (int(key) or 10) <= len(self.scene_names):
            self.set_scene((int(key) or 10) - 1)   # 0 picks the 10th
        elif key == "g":
            self.glow = not self.glow
            self.toast("Glow " + ("on" if self.glow else "off"), 2)
        elif key == "c":
            r = self.renderer
            r.truecolor = not r.truecolor
            r.reset()
            self.toast("True color" if r.truecolor else "256 colors", 2)
        elif key == "q":
            return False
        return True

    # ------------------------------------------------------------ drawing

    def draw_tracker(self, cv, y, color, t, pulse):
        """Focus sessions as a row of orbs joined by a path, ending in a star
        for the long break:  ●━━━●━━━◑───○   ✦
        Done sessions glow, the current one fills up as time passes."""
        tm = self.timer
        n = tm.cfg["sessions_before_long_break"]
        done = n if tm.phase == "long_break" else tm.completed % n
        current = done if tm.phase == "focus" else None
        dim = (75, 75, 100)
        cells = []   # (char, color, glow)
        for i in range(n):
            if i < done:
                cells.append(("●", color, 0.3))
            elif i == current:
                frac = 1 - tm.remaining / tm.length()
                ch = "○◔◑◕●"[min(4, int(frac * 5))]
                cells.append((ch, lerp(color, (255, 255, 255), 0.35 * pulse), 0.55 * pulse))
            else:
                cells.append(("○", dim, 0))
            if i < n - 1:
                lit = i < done
                seg = ("━", scale(color, 0.6), 0) if lit else ("─", (50, 50, 70), 0)
                cells += [seg] * 3
        cells += [(" ", dim, 0)] * 3
        if tm.phase == "long_break":
            twinkle = 0.75 + 0.25 * math.sin(t * 3)
            cells.append(("✦", scale((255, 225, 140), twinkle), 0.7 * twinkle))
        else:
            cells.append(("✧", (110, 100, 80), 0))

        x0 = (cv.w - len(cells)) // 2
        cv.dim_rect(x0 - 1, y, len(cells) + 2, 1, 0.25)
        for i, (ch, c, g) in enumerate(cells):
            if g:
                cv.glow(x0 + i, y, c, 1.5, g)
        for i, (ch, c, g) in enumerate(cells):
            if ch != " ":
                cv.put(x0 + i, y, ch, c)

    def frame(self, t):
        self.now = t
        cols, rows = shutil.get_terminal_size((80, 24))
        rows -= 1  # leave one line so the screen doesn't scroll
        cv = Canvas(cols, rows)
        cv.glow_on = self.glow
        self.scene.draw(cv, t)
        fade = (t - self.switched_at) / 0.6
        if fade < 1:
            cv.fade(max(0.0, fade))

        label, color = PHASES[self.timer.phase]
        running = self.timer.running
        if not running:
            color = PAUSED
        pulse = 0.8 + 0.2 * math.sin(t * 1.8) if running else 0.55

        # big glowing clock
        mins, secs = divmod(max(0, int(self.timer.remaining + 0.999)), 60)
        clock = f"{mins:02d}:{secs:02d}"
        width = sum(len(FONT[c][0]) for c in clock) + 2 * (len(clock) - 1)
        x0, y0 = (cols - width) // 2, 1
        cv.dim_rect(x0 - 3, y0 - 1, width + 6, 10, 0.2)
        light = lerp(color, (255, 255, 255), 0.6)
        shine_x = ((t * 0.35) % 2.5 - 0.5) * width if running else -99  # sweeping shine

        def pixel_color(px, py):
            c = lerp(light, scale(color, 0.85), py / 9)
            shine = math.exp(-((px - x0 - shine_x + py * 0.6) / 2.5) ** 2)
            return scale(lerp(c, (255, 255, 255), 0.6 * shine), 0.8 + 0.2 * pulse)

        x = x0
        for ch in clock:
            glyph = FONT[ch]
            for row in range(5):
                top, bottom = glyph[row * 2], glyph[row * 2 + 1]
                for dx in range(len(top)):
                    t_on, b_on = top[dx] == "#", bottom[dx] == "#"
                    if not (t_on or b_on):
                        continue
                    px, py = x + dx, y0 + row
                    cv.glow(px, py, color, 2, 0.06 * pulse)
                    if t_on and b_on:   # top pixel as text color, bottom as background
                        cv.put(px, py, "▀", pixel_color(px, row * 2))
                        cv.set_bg(px, py, pixel_color(px, row * 2 + 1))
                    elif t_on:
                        cv.put(px, py, "▀", pixel_color(px, row * 2))
                    else:
                        cv.put(px, py, "▄", pixel_color(px, row * 2 + 1))
            x += len(glyph[0]) + 2

        # phase name, session tracker, progress bar
        state = "  (paused - press space)" if not running else ""
        cv.center(y0 + 6, f"{label}{state}", color)
        self.draw_tracker(cv, y0 + 7, color, t, pulse)

        done = 1 - self.timer.remaining / self.timer.length()
        bar_w = max(10, width)
        filled = int(done * bar_w)
        bx = (cols - bar_w) // 2
        cv.dim_rect(bx - 1, y0 + 8, bar_w + 2, 1, 0.25)
        for i in range(bar_w):
            if i < filled:
                cv.put(bx + i, y0 + 8, "━", lerp(scale(color, 0.45), light, i / bar_w))
            else:
                cv.put(bx + i, y0 + 8, "─", (60, 60, 80))
        if 0 < filled and running:
            cv.glow(bx + filled - 1, y0 + 8, color, 1.5, 0.5 * pulse)
            cv.put(bx + filled - 1, y0 + 8, "━", (255, 255, 255))

        if self.timer.blocking:
            cv.center(y0 + 9, "blocking distractions", (150, 120, 255))

        now = time.time()
        self.toasts = [m for m in self.toasts if m[1] > now]
        if self.toasts:
            cv.center(y0 + 10, self.toasts[-1][0], (255, 140, 220))
        elif mac.last_error:
            cv.center(y0 + 10, mac.last_error, (255, 95, 95))

        # spotify + key help along the bottom
        if self.spotify:
            st, track, artist = self.spotify
            icon = "▶" if st == "playing" else "❚❚"
            music = f"♪ {icon}  {track} — {artist}"
        else:
            music = "♪ Spotify isn't open"
        cv.center(rows - 2, music, (130, 230, 140))
        cv.center(rows - 1, "space start/pause · s skip · r restart · ←/→ scene · "
                            "g glow · p/n/b music · q quit", (120, 120, 140))

        return self.renderer.render(cv)


# ---------------------------------------------------------------- main loop

ARROWS = {"\x1b[C": "right", "\x1bOC": "right", "\x1b[D": "left", "\x1bOD": "left"}


def read_keys(fd):
    """Return the key presses waiting on the keyboard (arrows become words)."""
    if not select.select([fd], [], [], 0)[0]:
        return []
    data = os.read(fd, 64).decode(errors="ignore")
    keys, i = [], 0
    while i < len(data):
        if data[i] == "\x1b":
            keys.append(ARROWS.get(data[i:i + 3], "esc"))
            i += 3 if data[i:i + 3] in ARROWS else 1
        else:
            keys.append(data[i].lower())
            i += 1
    return keys


def main():
    parser = argparse.ArgumentParser(description="Space-themed focus timer")
    parser.add_argument("--focus", type=float, help="focus minutes")
    parser.add_argument("--break", dest="brk", type=float, help="short break minutes")
    parser.add_argument("--scene", choices=list(SCENES), help="background to start on")
    parser.add_argument("--colors", choices=["auto", "truecolor", "256"], default="auto",
                        help="color mode (auto-detected by default)")
    args = parser.parse_args()

    cfg = load_config()
    if args.focus:
        cfg["focus_minutes"] = args.focus
    if args.brk:
        cfg["short_break_minutes"] = args.brk

    truecolor = supports_truecolor() if args.colors == "auto" else args.colors == "truecolor"
    app = App(cfg, scene=args.scene or cfg.get("scene"), truecolor=truecolor)
    Watcher(app).start()

    interactive = sys.stdin.isatty()
    fd = sys.stdin.fileno()
    if interactive:
        import termios
        import tty
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)  # read keys instantly, without Enter

    sys.stdout.write(CLEAR + HIDE_CURSOR)
    start = last = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            app.timer.tick(now - last)
            last = now

            keys = read_keys(fd) if interactive else []
            if not all(app.handle_key(k) for k in keys):
                break

            sys.stdout.write(app.frame(now - start))
            sys.stdout.flush()
            time.sleep(1 / FPS)
    except KeyboardInterrupt:
        pass
    finally:
        if interactive:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write(RESET + SHOW_CURSOR + CLEAR + HOME)
        print(f"Focus sessions completed: {app.timer.completed}")


if __name__ == "__main__":
    main()
