#!/usr/bin/env python3
"""Space-themed pomodoro focus timer for the macOS terminal.

While a focus session is running, apps on the blocklist in config.json are
quit automatically. Spotify (the desktop app) can be controlled from here.

Usage:
    python3 ascii_pomodoro.py                  # uses the times in config.json
    python3 ascii_pomodoro.py --focus 50 --break 10
    python3 ascii_pomodoro.py --focus 0.2 --break 0.1   # quick test (12s / 6s)

    python3 ascii_pomodoro.py --scene aurora   # start on a different background

Keys:
    space  start / pause         s  skip to next session
    r      restart this session  q  quit
    p      Spotify play/pause    n  next song    b  previous song
    left/right or [ ]  change background    1-9, 0, -  jump to a background
    g      glow on/off           c  true color / 256 color
    h      hide / show the key hints
    x      app blocker on/off      f  full screen on/off
    a      ambient space sounds on/off
"""

import argparse
import json
import math
import random
import os
import select
import shutil
import signal
import sys
import threading
import time

import mac
import sound
from canvas import ASPECT, Canvas, Renderer, lerp, scale, supports_truecolor
from scenes import SCENES

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
FPS = 20

CLEAR, HOME, RESET = "\033[2J", "\033[H", "\033[0m"
WRAP_OFF, WRAP_ON = "\033[?7l", "\033[?7h"   # lets us draw on the very last row
HIDE_CURSOR, SHOW_CURSOR = "\033[?25l", "\033[?25h"
# The alternate screen (like vim or less use): nothing drawn there ends up in
# the scrollback, and leaving it puts the terminal back exactly as it was.
ALT_SCREEN_ON, ALT_SCREEN_OFF = "\033[?1049h", "\033[?1049l"

PHASES = {                            # label, color
    "focus": ("FOCUS", (110, 195, 255)),
    "short_break": ("SHORT BREAK", (255, 120, 215)),
    "long_break": ("LONG BREAK", (175, 140, 255)),
}
PAUSED = (150, 150, 165)
ALERT_SECONDS = 3.5   # how long the "app closed" warning stays up

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
        self.block_apps = cfg.get("block_apps", True)   # x toggles this
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
        return self.phase == "focus" and self.running and self.block_apps


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
                self.app.toast("blocklist reloaded")
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
                        self.app.app_closed(name)


# ---------------------------------------------------------------- window padding

class Padding:
    """Keeps the strip of padding around the terminal's text grid the same
    color as the edges of the scene, so the art looks like it goes all the
    way to the edge of the window instead of sitting inside a border."""

    def __init__(self):
        self.apple = os.environ.get("TERM_PROGRAM") == "Apple_Terminal"
        self.tty = None
        self.original = None     # Terminal.app tab color to put back on quit
        self.sent = None
        self.sent_at = -99.0
        self.busy = threading.Lock()
        if self.apple:
            try:
                self.tty = os.ttyname(sys.stdout.fileno())
            except OSError:
                self.apple = False

    def update(self, color, now):
        """Returns escape codes to write (for terminals that take OSC 11)."""
        color = tuple(int(min(255, max(0, c))) for c in color)
        if self.sent and max(abs(a - b) for a, b in zip(color, self.sent)) < 4:
            return ""
        if now - self.sent_at < (0.6 if self.apple else 0.1):
            return ""
        self.sent, self.sent_at = color, now
        if not self.apple:
            return "\033]11;rgb:%02x/%02x/%02x\033\\" % color
        if self.busy.acquire(blocking=False):   # osascript is slow: do it off-thread
            def work(color=color):
                try:
                    if self.original is None:
                        self.original = mac.get_tab_background(self.tty) or ""
                    mac.set_tab_background(self.tty, color)
                finally:
                    self.busy.release()
            threading.Thread(target=work, daemon=True).start()
        else:
            self.sent = None   # try again next frame
        return ""

    def restore(self):
        if not self.apple:
            return "\033]111\033\\"
        with self.busy:
            if self.original:
                mac.set_tab_background(self.tty, self.original)
        return ""


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
        self.spotify = None          # what Spotify is playing (a dict) or None
        self.eq, self.eq_peak = [], []   # equalizer bar heights
        self.toasts = []             # (message, expires_at)
        self.closed = 0              # apps closed by the blocklist this run
        self.alert = None            # [app names, started_at] for the warning popup
        self.blocker_changed = -99.0 # when x was last pressed (for the switch effect)
        self.fullscreen = False      # is the window in full screen right now?
        self.fullscreen_by_us = False   # did we put it there? (undone on quit)
        self.fullscreen_busy = threading.Lock()
        self.show_keys = True
        self.now = 0.0
        self.padding = Padding()
        self.ambient = sound.Ambient(cfg.get("ambient_volume", 0.5), on_message=self.toast)
        if cfg.get("ambient_sound", True):
            self.ambient.start()

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

    def toggle_fullscreen(self, on=None):
        """f: go full screen, or come back out if we already are. on=True/False
        forces a direction. Runs in the background since macOS animates it."""
        def work():
            state = mac.is_fullscreen()            # ask the window, don't guess
            if isinstance(state, str):
                self.toast(state, 7)
                return
            target = (not state) if on is None else on
            if target != state:
                for _ in range(2):                 # retry once if macOS ignored us
                    error = mac.set_fullscreen(target)
                    if error:
                        self.toast(error, 7)
                        return
                    for _ in range(12):            # the animation takes ~1s
                        time.sleep(0.25)
                        if mac.is_fullscreen() == target:
                            break
                    else:
                        continue
                    break
            self.fullscreen = mac.is_fullscreen() is True
            if target and not state:
                self.fullscreen_by_us = True
            elif not target:
                self.fullscreen_by_us = False

        def guarded():
            if self.fullscreen_busy.acquire(blocking=False):   # ignore presses mid-switch
                try:
                    work()
                finally:
                    self.fullscreen_busy.release()
        threading.Thread(target=guarded, daemon=True).start()

    def app_closed(self, name):
        """Called by the watcher when it quits a blocked app."""
        self.closed += 1
        now = time.time()
        if self.alert and now - self.alert[1] < ALERT_SECONDS and name not in self.alert[0]:
            self.alert[0].append(name)   # several at once: list them together
            self.alert[1] = now
        else:
            self.alert = [[name], now]

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
            sp = self.spotify
            if key == "p" and sp and sp["state"] in ("playing", "paused"):   # flip it now,
                now = time.time()                                          # don't wait a second
                if sp["state"] == "playing":
                    sp["position"] += now - sp["at"]
                self.spotify = dict(sp, state="paused" if sp["state"] == "playing" else "playing",
                                    at=now)
            threading.Thread(target=mac.spotify_command, args=(command,), daemon=True).start()
        elif key in ("right", "]", "."):
            self.set_scene(self.scene_index + 1)
        elif key in ("left", "[", ","):
            self.set_scene(self.scene_index - 1)
        elif key.isdigit() and (int(key) or 10) <= len(self.scene_names):
            self.set_scene((int(key) or 10) - 1)   # 0 picks the 10th
        elif key == "-" and len(self.scene_names) >= 11:
            self.set_scene(10)
        elif key == "x":
            t.block_apps = not t.block_apps
            self.blocker_changed = time.time()
            self.toast("app blocker " + ("on" if t.block_apps else "off"), 2)
        elif key == "f":
            self.toggle_fullscreen()
        elif key == "a":
            on = self.ambient.toggle()
            self.toast("ambient sound " + ("on" if on else "off"), 2)
        elif key == "h":
            self.show_keys = not self.show_keys
        elif key == "g":
            self.glow = not self.glow
            self.toast("glow " + ("on" if self.glow else "off"), 2)
        elif key == "c":
            r = self.renderer
            r.truecolor = not r.truecolor
            r.reset()
            self.toast("true color" if r.truecolor else "256 colors", 2)
        elif key == "q":
            return False
        return True

    # ------------------------------------------------------------ drawing

    def draw_blocker(self, cv, y, t):
        """Status line under the progress bar during a focus session."""
        tm = self.timer
        since = time.time() - self.blocker_changed
        if not tm.block_apps:
            self.draw_blocker_off(cv, y, t, since)
            return
        n = len(tm.cfg["blocklist"])
        main = f"◆  blocking {n} app{'s' if n != 1 else ''}"
        extra = f"  ·  {self.closed} closed" if self.closed else ""
        x0 = (cv.w - len(main + extra)) // 2
        cv.dim_rect(x0, y, len(main + extra), 1, 1.0)
        if since < 0.7:   # just switched on: one fast bright sweep
            sweep, boost = since / 0.7 * (len(main) + 6) - 3, 1.0
        else:             # then a shimmer runs across now and then
            sweep, boost = (t * 9) % (len(main) + 25) - 5, 0.7
        for i, ch in enumerate(main):
            base = lerp((140, 115, 255), (100, 210, 255), i / len(main))
            shine = math.exp(-((i - sweep) / 2) ** 2)
            cv.put(x0 + i, y, ch, lerp(base, (255, 255, 255), boost * shine))
        cv.text(x0 + len(main), y, extra, (115, 115, 145))
        pulse = 0.6 + 0.4 * math.sin(t * 2.2)
        cv.glow(x0, y, (140, 120, 255), 1.2 + (since < 0.7) * 2, 0.4 * pulse + max(0, 0.7 - since))

    def draw_blocker_off(self, cv, y, t, since):
        """'app blocker off': a dying neon sign, with a glitch burst right
        after you switch it off and a red standby light that breathes."""
        main, hint = "◇  app blocker off", "  ·  x to turn on"
        text = main + hint
        x0 = (cv.w - len(text)) // 2
        cv.dim_rect(x0, y, len(text), 1, 1.0)
        tick = int(t * 14)
        rnd = random.Random(tick)
        glitching = since < 0.8
        flicker = 0.25 if rnd.random() < (0.5 if glitching else 0.06) else 1.0
        for i, ch in enumerate(text):
            if i >= len(main):
                cv.put(x0 + i, y, ch, (95, 95, 118))
                continue
            col = scale(lerp((255, 150, 95), (235, 95, 110), i / len(main)), flicker)
            dx = 0
            if glitching and ch != " " and random.Random(tick * 31 + i).random() < 0.3:
                ch = rnd.choice("▚▞░▒╳_")
                col = rnd.choice([(255, 60, 80), (90, 220, 255), (255, 255, 255)])
                dx = rnd.choice((-1, 0, 1))
            if ch != " ":
                cv.put(x0 + i + dx, y, ch, col)
        standby = 0.5 + 0.5 * math.sin(t * 1.6)
        cv.put(x0, y, "◇", lerp((120, 40, 50), (255, 80, 90), standby))
        cv.glow(x0, y, (255, 50, 70), 1.3, 0.35 * standby)
        if glitching:
            cv.glow(x0 + len(main) // 2, y, (255, 60, 90), 3, 0.35 * (1 - since / 0.8))

    def draw_alert(self, cv):
        """Warning popup that flashes when a blocked app gets closed."""
        if not self.alert:
            return
        names, start = self.alert
        age = time.time() - start
        if age > ALERT_SECONDS:
            self.alert = None
            return
        k = min(1.0, age / 0.1) * min(1.0, (ALERT_SECONDS - age) / 0.7)   # fade in / out
        flashing = age < 1.0
        flash = 1.0 if not flashing else (1.0 if int(age / 0.14) % 2 == 0 else 0.35)
        w, h = cv.w, cv.h

        # red glow creeping in from the edges of the screen
        edge = (255, 40, 50)
        strength = 0.6 * k * flash * math.exp(-age * 1.3)   # flashes, then fades
        for y in range(h):
            for x in list(range(min(10, w))) + list(range(max(10, w - 10), w)):
                d = min(x, w - 1 - x) / ASPECT
                d = min(d, y, h - 1 - y)
                cv.add_bg(x, y, scale(edge, strength * math.exp(-d / 1.3)))
        for y in list(range(min(4, h))) + list(range(max(4, h - 4), h)):
            for x in range(10, w - 10):
                d = min(y, h - 1 - y)
                cv.add_bg(x, y, scale(edge, strength * math.exp(-d / 1.3)))

        # the panel itself
        title = " + ".join(names).upper() + " CLOSED"
        left = int(self.timer.remaining) if self.timer.phase == "focus" else 0
        sub = f"blocked during focus  ·  {left // 60}:{left % 60:02d} left"
        pw = max(len(title) + 4, len(sub)) + 8
        ph = 6
        shake = int(round(2 * math.sin(age * 70))) if age < 0.35 else 0
        px = (w - pw) // 2 + shake
        py = int((min(13, h * 0.45) + h - 3) / 2) - ph // 2
        cv.dim_rect(px, py, pw, ph, 1 - 0.88 * k)
        for yy in range(py + 1, py + ph - 1):
            for xx in range(px + 1, px + pw - 1):
                cv.add_bg(xx, yy, scale((45, 6, 14), k))
        border = scale(lerp((255, 70, 70), (255, 200, 90), 1 - flash) if flashing
                       else (255, 85, 85), k)
        cv.text(px, py, "╭" + "─" * (pw - 2) + "╮", border)
        cv.text(px, py + ph - 1, "╰" + "─" * (pw - 2) + "╯", border)
        for yy in range(py + 1, py + ph - 1):
            cv.put(px, yy, "│", border)
            cv.put(px + pw - 1, yy, "│", border)
        for xx in range(px, px + pw, 3):
            cv.glow(xx, py, (255, 60, 60), 1.5, 0.12 * k * flash)
            cv.glow(xx, py + ph - 1, (255, 60, 60), 1.5, 0.12 * k * flash)
        tx = px + (pw - len(title) - 3) // 2
        cv.text(tx, py + 2, "⚠", scale((255, 195, 60), k))
        cv.glow(tx, py + 2, (255, 170, 40), 1.5, 0.5 * k * flash)
        cv.text(tx + 3, py + 2, title, scale((255, 240, 240), k))
        cv.text(px + (pw - len(sub)) // 2, py + 3, sub, scale((215, 150, 160), k))

    def draw_hud(self, cv, t, accent):
        """Bottom bar: now playing on the left, scene on the right, keys below.
        The background art fades out underneath instead of being boxed off."""
        w, h = cv.w, cv.h
        fades = (0.8, 0.6, 0.4, 0.28) if self.show_keys else (0.85, 0.7, 0.5)
        for k, f in enumerate(fades):
            cv.dim_row(h - len(fades) + k, f)

        row = h - 2 if self.show_keys else h - 1
        # scene name + a dot per scene, right-aligned
        n = len(self.scene_names)
        name = self.scene.name.lower()
        right = len(name) + 3 + n
        rx = w - 2 - right
        cv.text(rx - 1, row, " " + name + "   ", (185, 185, 210))
        for i in range(n):
            here = i == self.scene_index
            cv.put(rx + len(name) + 3 + i, row, "•" if here else "·",
                   accent if here else (80, 80, 105))
        cv.glow(rx + len(name) + 3 + self.scene_index, row, accent, 1, 0.3)

        # now playing, left-aligned
        self.draw_spotify(cv, t, row, max(0, rx - 4))

        if not self.show_keys:
            return
        # key hints: keys in color, labels gray; drop some if the window is narrow
        screen = "exit full screen" if self.fullscreen else "full screen"
        hints = [("space", "start/pause"), ("s", "skip"), ("r", "restart"), ("← →", "scene"),
                 ("g", "glow"), ("x", "blocker"), ("f", screen), ("a", "sound"), ("p n b", "music"),
                 ("h", "hide keys"),
                 ("q", "quit")]
        while hints and sum(len(k) + len(v) + 4 for k, v in hints) - 3 > w - 4:
            hints.pop(-3)
        total = sum(len(k) + len(v) + 4 for k, v in hints) - 3
        x = (w - total) // 2
        key_col = lerp(accent, (255, 255, 255), 0.2)
        cv.text(x - 1, h - 1, " " * (total + 2), (0, 0, 0))
        for key, label in hints:
            cv.text(x, h - 1, key, key_col)
            cv.text(x + len(key) + 1, h - 1, label, (105, 105, 128))
            x += len(key) + len(label) + 4

    def draw_spotify(self, cv, t, row, room):
        """Now playing: a bouncing equalizer next to the song, artist and a
        progress bar. Three rows tall, ending on `row`."""
        sp = self.spotify
        x = 2
        if not sp:
            cv.text(x, row, "♪  spotify isn't open "[:room + 8], (95, 95, 120))
            return
        playing = sp["state"] == "playing"
        GREEN, TEAL = (30, 215, 96), (60, 225, 200)
        if room < 24 or cv.h < 18:                           # tiny window: a one-row mini version
            for i in range(min(4, room)):
                level = 0.5 + 0.5 * math.sin(t * (4.5 + i * 1.7) + i * 1.3) if playing else 0
                cv.put(x + i, row, "▁▂▃▄▅▆▇"[int(level * 6)],
                       lerp((40, 120, 70), GREEN, level) if playing else (70, 90, 80))
            return
        top = row - 2
        card = min(room, 56)
        cv.soft_shade(x + card / 2, top + 1, card / 2 + 6, 3.2, 0.55)
        cv.dim_rect(x - 1, top, card + 1, 3, 1.0)           # clear stars out from behind it

        # the equalizer: 7 bars, 3 rows tall, thumping along to a beat
        beat = math.exp(-((t * 2.0) % 1.0) * 5)          # a kick about twice a second
        if len(self.eq) != 7:
            self.eq, self.eq_peak = [0.0] * 7, [0.0] * 7
        for i in range(7):
            if playing:
                wobble = 0.5 + 0.5 * math.sin(t * (3.1 + i * 1.37) + i * 2.1)
                wobble2 = 0.5 + 0.5 * math.sin(t * (7.3 - i * 0.6) + i)
                target = (0.04 + 0.45 * wobble + 0.18 * wobble2
                          + 0.4 * beat * (1 - abs(i - 3) / 4.5))
            else:
                target = 0.06
            ease = 0.5 if target > self.eq[i] else 0.2        # jump up fast, settle slower
            self.eq[i] += (min(1.0, target) - self.eq[i]) * ease
            self.eq_peak[i] = max(self.eq[i], self.eq_peak[i] - 0.015)
            eighths = int(self.eq[i] * 24)
            peak = int(self.eq_peak[i] * 24)
            col = lerp(GREEN, TEAL, i / 6) if playing else (70, 95, 82)
            bx = x + i * 2
            for r in range(3):                                # r = 0 is the bottom row
                e = max(0, min(8, eighths - r * 8))
                y = row - r
                if e:
                    cv.put(bx, y, " ▁▂▃▄▅▆▇█"[e], lerp(col, (220, 255, 235), 0.35 * r / 2))
                elif playing and peak // 8 == r and peak > eighths + 1:
                    cv.put(bx, y, "▁", lerp(col, (255, 255, 255), 0.5))   # falling peak marker
        if playing:
            cv.glow(x + 6, row - 0.5, GREEN, 3, 0.18 + 0.25 * beat)

        # song, artist and album
        tx = x + 16
        width = max(0, min(room - 16, 40))
        if width < 6:
            return
        dim = 1.0 if playing else 0.6
        if sp["state"] == "stopped":
            cv.text(tx, top, "spotify is open", scale((220, 220, 235), dim))
            cv.text(tx, top + 1, "press p to play", (120, 120, 145))
            return
        icon = "▶" if playing else "❚❚"
        tw = width - len(icon) - 1
        title = sp["track"]
        if len(title) > tw:
            if playing:                                       # scroll long titles
                loop = title + "   ·   "
                step = int(t * 4) % len(loop)
                title = (loop + loop)[step:step + tw]
            else:
                title = title[:tw - 1] + "…"
        cv.text(tx, top, icon, GREEN if playing else (150, 150, 165))
        cv.text(tx + len(icon) + 1, top, title, scale((240, 240, 250), dim))
        sub = sp["artist"] + (f"  ·  {sp['album']}" if sp["album"] else "")
        if len(sub) > width:
            sub = sub[:width - 1] + "…"
        cut = min(len(sub), len(sp["artist"]))
        cv.text(tx, top + 1, sub[:cut], scale((190, 175, 225), dim))
        cv.text(tx + cut, top + 1, sub[cut:], scale((120, 120, 150), dim))

        # progress bar with a glowing head, and the time
        dur = sp["duration"]
        pos = sp["position"] + (time.time() - sp["at"] if playing else 0)
        pos = max(0.0, min(dur, pos))
        clock = f"{int(pos) // 60}:{int(pos) % 60:02d} / {int(dur) // 60}:{int(dur) % 60:02d}"
        if width - len(clock) - 1 < 6:                         # no room for the time
            clock = ""
        bar = width - len(clock) - 1 if clock else width
        done = int(bar * pos / dur) if dur else 0
        for k in range(bar):
            if k < done:
                cv.put(tx + k, row, "━", scale(lerp(GREEN, TEAL, k / bar), 0.65 + 0.35 * dim))
            else:
                cv.put(tx + k, row, "─", (70, 70, 92))
        head = tx + min(done, bar - 1)
        cv.put(head, row, "●", (230, 255, 240) if playing else (160, 170, 165))
        if playing:
            cv.glow(head, row, GREEN, 1.3, 0.35 + 0.3 * beat)
        cv.text(tx + bar + 1, row, clock, (125, 125, 150))

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
        cv.dim_rect(x0, y, len(cells), 1, 1.0)
        for i, (ch, c, g) in enumerate(cells):
            if g:
                cv.glow(x0 + i, y, c, 1.5, g)
        for i, (ch, c, g) in enumerate(cells):
            if ch != " ":
                cv.put(x0 + i, y, ch, c)

    def frame(self, t):
        self.now = t
        cols, rows = shutil.get_terminal_size((80, 24))   # every row: autowrap is off
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
        x0, y0 = (cols - width) // 2, 2 if rows >= 24 else 1   # a little air above the clock
        cv.soft_shade(cols / 2, y0 + 4.5, width / 2 + 14, 8, 0.6)   # soft, no box
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
        cv.dim_rect(bx, y0 + 8, bar_w, 1, 1.0)
        for i in range(bar_w):
            if i < filled:
                cv.put(bx + i, y0 + 8, "━", lerp(scale(color, 0.45), light, i / bar_w))
            else:
                cv.put(bx + i, y0 + 8, "─", (60, 60, 80))
        if 0 < filled and running:
            cv.glow(bx + filled - 1, y0 + 8, color, 1.5, 0.5 * pulse)
            cv.put(bx + filled - 1, y0 + 8, "━", (255, 255, 255))

        if self.timer.phase == "focus" and running:
            self.draw_blocker(cv, y0 + 9, t)

        now = time.time()
        self.toasts = [m for m in self.toasts if m[1] > now]
        if self.toasts:
            cv.center(y0 + 10, self.toasts[-1][0], (255, 140, 220))
        elif mac.last_error:
            cv.center(y0 + 10, mac.last_error, (255, 95, 95))

        self.draw_hud(cv, t, light)
        pad = self.padding.update(cv.edge_color(), t) if fade >= 1 else ""
        self.draw_alert(cv)
        return self.renderer.render(cv) + pad


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
    parser.add_argument("--fullscreen", action="store_true",
                        help="put the terminal window in full screen")
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
    if args.fullscreen or cfg.get("fullscreen"):
        app.toggle_fullscreen(True)

    interactive = sys.stdin.isatty()
    fd = sys.stdin.fileno()
    if interactive:
        import termios
        import tty
        old_settings = termios.tcgetattr(fd)

    def enter_screen():
        if interactive:
            tty.setcbreak(fd)  # read keys instantly, without Enter
        sys.stdout.write(ALT_SCREEN_ON + CLEAR + HIDE_CURSOR + WRAP_OFF)
        sys.stdout.flush()
        app.renderer.reset()

    def leave_screen():
        if interactive:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        try:
            sys.stdout.write(RESET + WRAP_ON + SHOW_CURSOR + ALT_SCREEN_OFF)
            sys.stdout.flush()
        except OSError:        # the window is already gone
            pass

    # Signal handlers only leave a note: the main loop acts on it between
    # frames, so a half-written frame never gets mixed up with the clean-up.
    pending = set()

    def on_signal(signum, frame):
        pending.add("suspend" if signum == signal.SIGTSTP else "close")

    def suspend():
        """ctrl+z: hand the terminal back cleanly, pick up again on `fg`."""
        was_playing = app.ambient.on
        app.ambient.stop()
        leave_screen()
        signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTSTP)          # actually stop here...
        signal.signal(signal.SIGTSTP, on_signal)      # ...and carry on after `fg`
        enter_screen()
        if was_playing:
            app.ambient.start()

    # closing the tab/window (SIGHUP), `kill` (SIGTERM), ctrl+c (SIGINT) and
    # ctrl+\ (SIGQUIT) all go through the same clean-up as pressing q
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT, signal.SIGINT):
        signal.signal(sig, on_signal)
    if interactive:
        signal.signal(signal.SIGTSTP, on_signal)
    enter_screen()
    start = last = time.monotonic()
    try:
        while True:
            if "close" in pending:
                break
            if "suspend" in pending:
                pending.discard("suspend")
                suspend()
                last = time.monotonic()               # don't count the time spent stopped
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
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT, signal.SIGINT):
            signal.signal(sig, signal.SIG_IGN)   # don't get interrupted while tidying up
        app.ambient.stop()
        try:
            sys.stdout.write(app.padding.restore())
        except OSError:
            pass
        leave_screen()
        if app.fullscreen_by_us:   # put the window back how we found it
            mac.set_fullscreen(False)
        try:
            print(f"Focus sessions completed: {app.timer.completed}")
        except OSError:
            pass


if __name__ == "__main__":
    main()
