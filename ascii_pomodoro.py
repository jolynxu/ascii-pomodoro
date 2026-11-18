#!/usr/bin/env python3
"""Space-themed pomodoro focus timer for the macOS terminal.

While a focus session is running, apps on the blocklist in config.json are
quit automatically. Spotify (the desktop app) can be controlled from here.

Usage:
    python3 focus.py                  # uses the times in config.json
    python3 focus.py --focus 50 --break 10
    python3 focus.py --focus 0.2 --break 0.1   # quick test (12s / 6s)

Keys:
    space  start / pause         s  skip to next session
    r      restart this session  q  quit
    p      Spotify play/pause    n  next song    b  previous song
"""

import argparse
import json
import os
import select
import shutil
import sys
import threading
import time

import mac
from scene import SpaceScene

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
FPS = 20

CLEAR, HOME, RESET = "\033[2J", "\033[H", "\033[0m"
HIDE_CURSOR, SHOW_CURSOR = "\033[?25l", "\033[?25h"

PHASES = {
    "focus": ("FOCUS", 117),          # label, color (light blue)
    "short_break": ("SHORT BREAK", 213),
    "long_break": ("LONG BREAK", 141),
}

# Big clock digits, 3 wide x 5 tall (each block is doubled when drawn)
FONT = {
    "0": ["###", "# #", "# #", "# #", "###"], "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["###", "  #", "###", "#  ", "###"], "3": ["###", "  #", "###", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"], "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"], "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"], "9": ["###", "# #", "###", "  #", "###"],
    ":": [" ", "#", " ", "#", " "],
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
    def __init__(self, cfg):
        self.timer = Timer(cfg)
        self.scene = SpaceScene()
        self.spotify = None          # (state, track, artist) or None
        self.toasts = []             # (message, expires_at)

    def toast(self, msg, seconds=4):
        self.toasts.append((msg, time.time() + seconds))

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
        elif key == "q":
            return False
        return True

    # ------------------------------------------------------------ drawing

    def frame(self, t):
        cols, rows = shutil.get_terminal_size((80, 24))
        rows -= 1  # leave one line so the screen doesn't scroll
        grid = [[" "] * cols for _ in range(rows)]

        R = max(2.5, min(rows * 0.15, cols / 12))
        self.scene.draw(grid, t, cols / 2, rows * 0.66, R)

        label, color = PHASES[self.timer.phase]
        if not self.timer.running:
            color = 244  # gray while paused

        # big clock
        mins, secs = divmod(max(0, int(self.timer.remaining + 0.999)), 60)
        clock = f"{mins:02d}:{secs:02d}"
        widths = [len(FONT[c][0]) * 2 for c in clock]
        width = sum(widths) + 2 * (len(clock) - 1)
        x0, y0 = (cols - width) // 2, 1
        self.clear_box(grid, x0 - 2, y0 - 1, width + 4, 7)
        x = x0
        for ch, w in zip(clock, widths):
            for dy, line in enumerate(FONT[ch]):
                for dx, bit in enumerate(line):
                    if bit == "#":
                        self.text(grid, x + dx * 2, y0 + dy, "██", color)
            x += w + 2

        # status, progress bar, messages
        state = "" if self.timer.running else "  (paused - press space)"
        dots = "".join("●" if i < self.timer.completed % self.timer.cfg["sessions_before_long_break"]
                       else "○" for i in range(self.timer.cfg["sessions_before_long_break"]))
        self.center(grid, y0 + 6, f"{label}  {dots}{state}", color)

        done = 1 - self.timer.remaining / self.timer.length()
        bar_w = max(10, width)
        filled = int(done * bar_w)
        self.center(grid, y0 + 7, "━" * filled + "─" * (bar_w - filled), color)

        if self.timer.blocking:
            self.center(grid, y0 + 8, "blocking distractions", 99)

        now = time.time()
        self.toasts = [m for m in self.toasts if m[1] > now]
        if self.toasts:
            self.center(grid, y0 + 9, self.toasts[-1][0], 213)
        elif mac.last_error:
            self.center(grid, y0 + 9, mac.last_error, 203)

        # spotify + key help along the bottom
        if self.spotify:
            st, track, artist = self.spotify
            icon = "▶" if st == "playing" else "❚❚"
            music = f"♪ {icon}  {track} — {artist}"
        else:
            music = "♪ Spotify isn't open"
        self.center(grid, rows - 2, music[:cols - 4], 120)
        self.center(grid, rows - 1,
                    "space start/pause · s skip · r restart · p/n/b music · q quit", 240)

        return HOME + "\n".join("".join(row) for row in grid) + RESET

    @staticmethod
    def text(grid, x, y, s, color):
        if not 0 <= y < len(grid):
            return
        for i, ch in enumerate(s):
            if 0 <= x + i < len(grid[0]):
                grid[y][x + i] = f"\033[38;5;{color}m{ch}"

    def center(self, grid, y, s, color):
        x = (len(grid[0]) - len(s)) // 2
        self.clear_box(grid, x - 1, y, len(s) + 2, 1)
        self.text(grid, x, y, s, color)

    @staticmethod
    def clear_box(grid, x, y, w, h):
        for yy in range(max(0, y), min(len(grid), y + h)):
            for xx in range(max(0, x), min(len(grid[0]), x + w)):
                grid[yy][xx] = " "


# ---------------------------------------------------------------- main loop

def read_key():
    """Return a key press if there is one waiting, else None."""
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1).lower()
    return None


def main():
    parser = argparse.ArgumentParser(description="Space-themed focus timer")
    parser.add_argument("--focus", type=float, help="focus minutes")
    parser.add_argument("--break", dest="brk", type=float, help="short break minutes")
    args = parser.parse_args()

    cfg = load_config()
    if args.focus:
        cfg["focus_minutes"] = args.focus
    if args.brk:
        cfg["short_break_minutes"] = args.brk

    app = App(cfg)
    Watcher(app).start()

    interactive = sys.stdin.isatty()
    if interactive:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)  # read keys instantly, without Enter

    sys.stdout.write(CLEAR + HIDE_CURSOR)
    start = last = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            app.timer.tick(now - last)
            last = now

            key = read_key() if interactive else None
            if key and not app.handle_key(key):
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
