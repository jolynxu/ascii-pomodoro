"""Ambient space sounds: a slow drone, drifting solar wind, twinkling chimes
and the odd far-off radio blip.

The sound is made right here with plain math (no extra packages), saved once
as a .wav file in your cache folder, then looped with `afplay` (built into
every Mac). Each loop fades in and out, and the next one starts while the
last one is fading, so there's no gap.
"""

import array
import math
import os
import random
import subprocess
import tempfile
import threading
import wave

RATE = 22050          # samples per second (plenty for soft ambient sound)
LOOP = 60.0           # seconds between loop starts
FADE = 4.0            # seconds of overlap between one loop and the next
VERSION = 1           # bump to regenerate the file after changing the sound

TAU = math.tau
_making = threading.Lock()   # only make the file once at a time


def cache_path():
    base = os.path.expanduser("~/Library/Caches")
    if not os.path.isdir(base):
        base = tempfile.gettempdir()
    folder = os.path.join(base, "ascii_pomodoro")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"space_ambient_v{VERSION}.wav")


# ---------------------------------------------------------------- making the sound

def _make(path):
    rnd = random.Random(42)
    n = int((LOOP + FADE) * RATE)
    out = [0.0] * n
    table_size = 4096
    table = [math.sin(TAU * i / table_size) for i in range(table_size)]

    # 1. the drone: a low, open chord whose notes slowly swell in and out
    #    (freq Hz, loudness, swell period s, swell phase); a few pairs are
    #    slightly detuned so they beat gently against each other
    notes = [(55.0, 0.30, 23, 0.0), (55.25, 0.20, 31, 1.0), (82.41, 0.18, 19, 2.0),
             (110.0, 0.14, 29, 3.0), (110.4, 0.10, 17, 4.5), (164.81, 0.07, 37, 1.5),
             (246.94, 0.035, 13, 5.0)]
    block = 64                                   # loudness changes are worked out per block
    for freq, amp, period, ph in notes:
        step = freq * table_size / RATE
        pos = rnd.uniform(0, table_size)
        for b in range(0, n, block):
            tt = b / RATE
            a = amp * (0.55 + 0.45 * math.sin(TAU * tt / period + ph))
            for i in range(b, min(n, b + block)):
                out[i] += a * table[int(pos) % table_size]
                pos += step

    # 2. solar wind: soft filtered noise that rises and falls like breathing
    lp1 = lp2 = lp3 = 0.0
    rr = rnd.random
    for b in range(0, n, block):
        tt = b / RATE
        swell = 0.5 + 0.5 * math.sin(TAU * tt / 14 + 0.7) * math.sin(TAU * tt / 41)
        c = 0.012 + 0.05 * swell                   # brighter when it swells
        a = 0.18 + 0.5 * swell
        for i in range(b, min(n, b + block)):
            lp1 += c * (rr() * 2 - 1 - lp1)
            lp2 += c * (lp1 - lp2)
            lp3 += 0.003 * (lp2 - lp3)
            out[i] += a * (lp2 - lp3) * 6

    # 3. chimes: high, glassy pings (like stars twinkling) with long echoes,
    #    plus a few faint radio blips and slow passing whooshes
    fx = [0.0] * n
    scale_hz = [659.26, 739.99, 880.0, 987.77, 1108.73, 1318.51, 1479.98, 1760.0]
    t = 1.5
    while t < LOOP + FADE - 4:
        f = rnd.choice(scale_hz)
        start, length = int(t * RATE), int(rnd.uniform(2.5, 4.0) * RATE)
        amp = rnd.uniform(0.05, 0.11)
        step = f * table_size / RATE
        step2 = f * 2.76 * table_size / RATE       # a bell-like overtone
        pos = pos2 = 0.0
        for k in range(min(length, n - start)):
            env = amp * math.exp(-k / (RATE * 0.7)) * min(1.0, k / 200)
            fx[start + k] += env * (table[int(pos) % table_size] + 0.25 * table[int(pos2) % table_size])
            pos += step
            pos2 += step2
        t += rnd.uniform(2.0, 6.5)

    t = 9.0
    while t < LOOP - 3:                            # radio blips, in little groups
        f = rnd.choice((1046.5, 1174.7, 1568.0))
        step = f * table_size / RATE
        for j in range(rnd.choice((2, 3))):
            start = int((t + j * 0.16) * RATE)
            length = int(0.07 * RATE)
            pos = 0.0
            for k in range(max(0, min(length, n - start))):
                env = 0.035 * math.sin(math.pi * k / length)
                fx[start + k] += env * table[int(pos) % table_size]
                pos += step
        t += rnd.uniform(11, 19)

    for t0 in (18.0, 47.0):                         # whooshes: noise sweeping up and away
        start, length = int(t0 * RATE), int(7 * RATE)
        lp = 0.0
        for k in range(min(length, n - start)):
            q = k / length
            env = 0.22 * math.sin(math.pi * q) ** 2
            c = 0.01 + 0.08 * math.sin(math.pi * q)
            lp += c * (rr() * 2 - 1 - lp)
            fx[start + k] += env * lp * 4

    for delay, gain in ((0.37, 0.45), (0.61, 0.35)):  # echoes for everything in fx
        d = int(delay * RATE)
        for i in range(d, n):
            fx[i] += fx[i - d] * gain
    for i in range(n):
        out[i] += fx[i]

    # fade the ends so overlapping loops blend into each other
    f = int(FADE * RATE)
    for k in range(f):
        g = math.sin(0.5 * math.pi * k / f)
        out[k] *= g
        out[n - 1 - k] *= g
    peak = max(1e-6, max(abs(v) for v in out))
    k = 0.8 * 32767 / peak
    data = array.array("h", (int(v * k) for v in out))

    tmp = path + ".part"
    with wave.open(tmp, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(data.tobytes())
    os.replace(tmp, path)


# ---------------------------------------------------------------- playing it

class Ambient:
    """Loops the ambient sound in the background. Call toggle() to switch it
    on and off; on_message(text) is called with anything worth showing."""

    def __init__(self, volume=0.5, on_message=None):
        self.volume = max(0.0, min(1.0, volume))
        self.on = False
        self.on_message = on_message or (lambda msg: None)
        self.procs = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.run_id = 0

    def toggle(self):
        if self.on:
            self.stop()
        else:
            self.start()
        return self.on

    def start(self):
        if self.on:
            return
        self.on = True
        self.run_id += 1
        self.wake = threading.Event()
        threading.Thread(target=self._loop, args=(self.run_id, self.wake), daemon=True).start()

    def stop(self):
        self.on = False
        self.wake.set()
        with self.lock:
            for p in self.procs:
                if p.poll() is None:
                    p.terminate()
            self.procs = []

    def _loop(self, run_id, wake):
        try:
            path = cache_path()
            with _making:
                if not os.path.exists(path):
                    self.on_message("tuning in to space sounds…")
                    _make(path)
        except Exception:
            self.on_message("couldn't make the space sounds")
            self.on = False
            return
        while self.on and run_id == self.run_id:
            try:
                p = subprocess.Popen(["afplay", "-v", f"{self.volume:.2f}", path],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                self.on_message("sound needs afplay (it comes with macOS)")
                self.on = False
                return
            with self.lock:
                if not self.on or run_id != self.run_id:   # switched off meanwhile
                    p.terminate()
                    return
                self.procs = [q for q in self.procs if q.poll() is None] + [p]
            if wake.wait(LOOP):
                return
