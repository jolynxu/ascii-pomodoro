"""Ambient space sounds: white noise, typing, dings and radio chatter from orbit.

There are several tracks to pick from (`t` flips through them in the timer):

    static      cosmic static: soft, even white noise, the hiss left over from the big bang
    deepspace   deep space: low brown noise that slowly breathes in and out
    console     comms console: typing at a console, radio calls, data bursts and a beacon
    observatory observatory: a soft drone, gentle typing, glassy dings and space whistles
    station     space station: cabin fans, humming equipment, the odd beep and call
    mission     mission control: radio chatter with Quindar beeps, crackle and squelch
    shortwave   shortwave: drifting static, morse code, tuning whistles and a pulsar

Every sound is made right here with plain math (no extra packages). The first
time a track plays it's worked out in a separate process (so the animation
doesn't stutter), saved as a .wav file in your cache folder, then looped with
`afplay` (built into every Mac). Each loop fades in and out, and the next one
starts while the last one is fading, so there's no gap.

Try them from the command line:

    python3 sound.py                  # list the tracks
    python3 sound.py mission          # play one loop of a track
    python3 sound.py --make all       # make every track ahead of time
"""

import array
import math
import os
import random
import subprocess
import sys
import tempfile
import threading
import wave

RATE = 22050          # samples per second (plenty for soft ambient sound)
LOOP = 60.0           # seconds between loop starts
FADE = 4.0            # seconds of overlap between one loop and the next
VERSION = 3           # bump to regenerate the files after changing the sound
N = int((LOOP + FADE) * RATE)

TAU = math.tau
sin, cos, exp, tanh, pi = math.sin, math.cos, math.exp, math.tanh, math.pi


def sec(t):
    return int(t * RATE)


# ---------------------------------------------------------------- building blocks
# Every signal is a plain list of floats, one per sample.

def white(rnd, n=N):
    r = rnd.random
    return [r() * 2.0 - 1.0 for _ in range(n)]


def pink(x):
    """White noise -> pink noise (equal energy per octave; softer, like rain)."""
    b0 = b1 = b2 = 0.0
    out = [0.0] * len(x)
    for i, w in enumerate(x):
        b0 = 0.99765 * b0 + w * 0.0990460
        b1 = 0.96300 * b1 + w * 0.2965164
        b2 = 0.57000 * b2 + w * 1.0526913
        out[i] = (b0 + b1 + b2 + w * 0.1848) * 0.25
    return out


def brown(x, leak=0.997):
    """White noise -> brown noise (a deep rumble, like a distant waterfall)."""
    y = 0.0
    out = [0.0] * len(x)
    for i, w in enumerate(x):
        y = leak * y + w * 0.04
        out[i] = y
    return out


def lowpass(x, hz):
    c = 1 - exp(-TAU * hz / RATE)
    y = 0.0
    out = [0.0] * len(x)
    for i, v in enumerate(x):
        y += c * (v - y)
        out[i] = y
    return out


def highpass(x, hz):
    return [a - b for a, b in zip(x, lowpass(x, hz))]


def biquad(x, kind, hz, q=0.707):
    """A sharper filter: "lp", "hp" or "bp" (band-pass)."""
    w = TAU * hz / RATE
    cs, al = cos(w), sin(w) / (2 * q)
    if kind == "lp":
        b0, b1, b2 = (1 - cs) / 2, 1 - cs, (1 - cs) / 2
    elif kind == "hp":
        b0, b1, b2 = (1 + cs) / 2, -(1 + cs), (1 + cs) / 2
    else:
        b0, b1, b2 = al, 0.0, -al
    a0 = 1 + al
    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, -2 * cs / a0, (1 - al) / a0
    x1 = x2 = y1 = y2 = 0.0
    out = [0.0] * len(x)
    for i, v in enumerate(x):
        y = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, y
        out[i] = y
    return out


def shifted(x):
    """The same noise half a loop later: sounds like a separate channel, which
    gives stereo width for free."""
    h = len(x) // 2
    return x[h:] + x[:h]


def envelope(x, fn, block=256):
    """Multiply x by fn(seconds), worked out once per block (in place)."""
    for b in range(0, len(x), block):
        g = fn(b / RATE)
        x[b:b + block] = [v * g for v in x[b:b + block]]
    return x


def add(dst, src, start, gain=1.0):
    end = min(len(dst), start + len(src))
    for i in range(max(0, start), end):
        dst[i] += src[i - start] * gain


def place(L, R, src, t, gain=1.0, pan=0.0):
    """Mix a sound into both channels at time t; pan runs -1 (left) to 1 (right)."""
    a = (pan + 1) * pi / 4
    add(L, src, sec(t), gain * cos(a) * 1.41)
    add(R, src, sec(t), gain * sin(a) * 1.41)


def silence(t):
    return [0.0] * sec(t)


def tone(hz, t, edge=0.006, decay=None):
    """A sine beep with soft edges (and an optional ring-out, in seconds)."""
    n, e = sec(t), max(1, sec(edge))
    w = TAU * hz / RATE
    out = []
    for k in range(n):
        g = min(1.0, k / e, (n - k) / e)
        if decay:
            g *= exp(-k / (decay * RATE))
        out.append(g * sin(w * k))
    return out


def slow(t, *waves):
    """A smooth 0-1 wobble built from (period, phase) sine pairs."""
    v = sum(sin(TAU * t / p + ph) for p, ph in waves) / len(waves)
    return 0.5 + 0.5 * v


# ---------------------------------------------------------------- radio voices

# (first, second formant) in Hz for a handful of vowel sounds
VOWELS = ((730, 1090), (530, 1840), (270, 2290), (570, 840), (300, 870),
          (660, 1720), (490, 1350), (400, 2000), (640, 1190))


def babble(rnd, seconds, pitch):
    """Speech-like mumbling with no actual words: a buzzing 'voice' shaped
    into vowel sounds syllable by syllable, with the odd hiss for consonants."""
    n = sec(seconds)
    plan, t = [], sec(0.05)
    while t < n - sec(0.3):
        words = rnd.randint(1, 4)
        for j in range(words):
            d = sec(rnd.uniform(0.07, 0.2))
            if t + d > n:
                break
            # pitch wanders a bit and drops toward the end of each phrase
            f0 = pitch * rnd.uniform(0.9, 1.15) * (1 - 0.05 * j / words)
            plan.append((t, d, rnd.choice(VOWELS), rnd.random() > 0.16, f0))
            t += d
        t += sec(rnd.uniform(0.04, 0.16) if rnd.random() < 0.8 else rnd.uniform(0.3, 0.6))

    out = [0.0] * n
    r = rnd.random
    l1 = b1 = l2 = b2 = 0.0
    c1, c2 = 500.0, 1500.0
    phase = 0.0
    g1 = g2 = 0.1
    for start, length, (t1, t2), voiced, f0 in plan:
        if not voiced:
            t1, t2 = 2600, 3600            # a hissy 's'/'sh' sound
        step = f0 / RATE
        for k in range(length):
            if k % 32 == 0:                 # glide the vowel shape toward its target
                c1 += (t1 - c1) * 0.3
                c2 += (t2 - c2) * 0.3
                g1, g2 = 2 * sin(pi * c1 / RATE), 2 * sin(pi * c2 / RATE)
                amp = sin(pi * k / length) ** 0.6
            if voiced:
                phase += step
                if phase >= 1.0:
                    phase -= 1.0
                src = 2 * phase - 1 + 0.2 * (r() * 2 - 1)
            else:
                src = 0.5 * (r() * 2 - 1)
            l1 += g1 * b1                   # two resonant filters = the mouth shape
            b1 += g1 * (src - l1 - 0.22 * b1)
            l2 += g2 * b2
            b2 += g2 * (src - l2 - 0.3 * b2)
            out[start + k] = amp * (b1 + 0.7 * b2)
    return out


def normalize(x, peak=1.0):
    m = max(1e-9, max(abs(v) for v in x))
    return [v * peak / m for v in x]


def radio(x, rnd, drive=3.0, hiss=0.12):
    """Make a sound come through a walkie-talkie: thin, crunchy and hissy."""
    x = normalize(biquad(biquad(x, "hp", 380), "lp", 2700))
    x = [tanh(drive * v) for v in x]
    noise = biquad(white(rnd, len(x)), "lp", 3800)
    x = [v + hiss * w for v, w in zip(x, noise)]
    return biquad(x, "lp", 3300)


def squelch(rnd, t=0.2):
    """The 'kshh' a radio makes when someone lets go of the button."""
    n = sec(t)
    noise = biquad(white(rnd, n), "hp", 900)
    return [v * 0.7 * exp(-k / (0.06 * RATE)) * min(1.0, k / 40) for k, v in enumerate(noise)]


def transmission(rnd, kind):
    """One message over the radio. "capcom" (the ground) opens and closes with
    Apollo-style Quindar beeps; "crew" (the ship) is noisier and ends in a squelch."""
    if kind == "capcom":
        voice = radio(babble(rnd, rnd.uniform(2.2, 5.0), rnd.uniform(105, 135)), rnd, 2.5, 0.1)
        beep_in = [v * 0.45 for v in tone(2525, 0.25)]
        beep_out = [v * 0.45 for v in tone(2475, 0.25)]
        return beep_in + silence(0.1) + voice + silence(0.08) + beep_out
    voice = radio(babble(rnd, rnd.uniform(1.8, 4.2), rnd.uniform(120, 190)), rnd, 4.0, 0.22)
    crackle(rnd, voice, 0, len(voice) / RATE, rate=10, gain=0.5)
    return squelch(rnd, 0.06) + voice + squelch(rnd, 0.22)


def crackle(rnd, dst, t0, t1, rate=6.0, gain=1.0):
    """Little pops and clicks, like static on an old radio (added into dst)."""
    t = t0 + rnd.expovariate(rate)
    while t < t1:
        n = sec(rnd.uniform(0.001, 0.012))
        a = gain * rnd.uniform(0.1, 1.0) ** 2
        start = sec(t)
        for k in range(n):
            if start + k < len(dst):
                dst[start + k] += a * (rnd.random() * 2 - 1) * exp(-k / (n * 0.3 + 1))
        t += rnd.expovariate(rate)


MORSE = {"A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.",
         "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.",
         "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.", "S": "...", "T": "-", "U": "..-",
         "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--", "Z": "--..", "0": "-----",
         "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....", "6": "-....",
         "7": "--...", "8": "---..", "9": "----."}


def morse(text, hz, wpm):
    """Morse code beeps for some text."""
    unit = 1.2 / wpm
    out = []
    for word in text.split():
        for letter in word:
            for mark in MORSE[letter]:
                out += tone(hz, unit * (3 if mark == "-" else 1), edge=0.005) + silence(unit)
            out += silence(unit * 2)
        out += silence(unit * 4)
    return out


def callsign(rnd):
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return (rnd.choice("KWN") + rnd.choice(letters) + str(rnd.randint(0, 9))
            + "".join(rnd.choice(letters) for _ in range(rnd.randint(2, 3))))


# ---------------------------------------------------------------- the tracks
# Each returns (left, right) lists N samples long. Anything that happens at a
# particular moment is kept between FADE and LOOP so it never lands in the
# overlap between one loop and the next.

def make_static(rnd):
    """Soft, even white noise with a faint, slow breath and the odd crackle."""
    x = lowpass(white(rnd), 6500)
    L, R = x, shifted(x)
    breath = lambda t: 0.94 + 0.06 * sin(TAU * t / 16)
    envelope(L, breath)
    envelope(R, breath)
    crackle(rnd, L, FADE, LOOP, rate=0.8, gain=0.7)
    crackle(rnd, R, FADE, LOOP, rate=0.8, gain=0.7)
    return L, R


def make_deepspace(rnd):
    """Brown noise that swells and darkens like slow breathing."""
    x = brown(white(rnd))
    out = []
    for ch in (x, shifted(x)):
        y = 0.0
        res = [0.0] * N
        for b in range(0, N, 256):     # the filter opens up a little on each swell
            s = slow(b / RATE, (13, 0.0), (31, 1.3))
            c = 1 - exp(-TAU * (180 + 520 * s) / RATE)
            g = 0.7 + 0.3 * s
            for i in range(b, min(N, b + 256)):
                y += c * (ch[i] - y)
                res[i] = y * g
        out.append(res)
    return out[0], out[1]


def keystroke(rnd, weight=1.0):
    """One key going down: a sharp plastic click, a little rattle and a soft
    thock from the keyboard's body. Bigger keys (weight > 1) sound deeper."""
    n = sec(0.07)
    click = biquad(white(rnd, n), "hp", rnd.uniform(2800, 4000))
    rattle = biquad(white(rnd, n), "bp", rnd.uniform(1100, 1900), 2)
    body = biquad(white(rnd, n), "bp", rnd.uniform(220, 420) / weight, 4)
    out = []
    for k in range(n):
        out.append(0.6 * click[k] * exp(-k / (0.0018 * RATE))
                   + 1.2 * rattle[k] * exp(-k / (0.006 * RATE))
                   + 2.5 * weight * body[k] * exp(-k / (0.014 * RATE * weight)))
    return out


def data_burst(rnd, seconds):
    """A modem-like squeal of data: two tones flipping back and forth for 1s and 0s."""
    lo, hi = rnd.choice(((1070, 1270), (1200, 2200), (2025, 2225)))
    baud = rnd.choice((150, 300, 600))
    n, per_bit = sec(seconds), RATE // baud
    out, ph, f = [], 0.0, lo
    for k in range(n):
        if k % per_bit == 0:
            f = hi if rnd.random() < 0.5 else lo
        ph += TAU * f / RATE
        out.append(sin(ph) * min(1.0, k / 200, (n - k) / 200))
    return radio(out, rnd, drive=1.5, hiss=0.15)


def make_console(rnd):
    """Someone at a comms console: bursts of typing, radio calls coming in,
    data squealing down the line and a satellite beacon beeping away."""
    w = white(rnd)
    room = [a + 0.3 * b for a, b in zip(lowpass(pink(w), 1500), brown(shifted(w)))]
    L, R = room, shifted(room)
    hum = [0.02 * sin(TAU * 120 * i / RATE) + 0.01 * sin(TAU * 240 * i / RATE) for i in range(N)]
    for i in range(N):
        L[i] = 0.25 * L[i] + hum[i]
        R[i] = 0.25 * R[i] + hum[i]

    keys = [keystroke(rnd) for _ in range(14)]           # one keyboard's worth of sounds
    ups = [[v * 0.35 for v in keystroke(rnd)] for _ in range(4)]
    space = [keystroke(rnd, 1.6) for _ in range(2)]
    enter = keystroke(rnd, 1.35)

    def press(sound, t, gain):
        pan = rnd.uniform(-0.3, 0.3)
        place(L, R, sound, t, gain * rnd.uniform(0.75, 1.0), pan)
        place(L, R, rnd.choice(ups), t + rnd.uniform(0.05, 0.1), gain, pan)   # key coming back up

    def typing(t, until):
        """Type words until `until`; returns when it stopped."""
        while t < until:
            for _ in range(rnd.randint(2, 8)):
                press(rnd.choice(keys), t, 0.75)
                t += max(0.045, rnd.gauss(0.12, 0.04))
            if rnd.random() < 0.1:                      # oops: backspace a few
                t += rnd.uniform(0.2, 0.5)
                for _ in range(rnd.randint(2, 5)):
                    press(keys[0], t, 0.75)
                    t += rnd.uniform(0.07, 0.1)
            if rnd.random() < 0.15:                     # end of a line
                t += rnd.uniform(0.2, 0.6)
                press(enter, t, 1.0)
                t += rnd.uniform(0.6, 1.8)
            else:
                press(rnd.choice(space), t, 0.85)
                t += max(0.08, rnd.gauss(0.16, 0.05))
                if rnd.random() < 0.12:                 # stop and think
                    t += rnd.uniform(0.5, 1.8)
        return t

    # a shuffled deck of what happens between bursts of typing, so every
    # loop gets a mix of calls, data and a beacon
    deck = ["radio", "data", "beacon", "radio", "data"]
    rnd.shuffle(deck)
    t, last = FADE + 0.4, "radio"
    while t < LOOP - 3 and deck:
        if last != "typing":
            t = typing(t, min(LOOP - 2, t + rnd.uniform(2.5, 7))) + rnd.uniform(0.3, 1.2)
            last = "typing"
            continue
        pick = deck.pop()
        if pick == "radio" and t > LOOP - 9:
            pick = "data"                               # no room left for a whole call
        if pick == "radio":                             # a call comes in
            msg = transmission(rnd, rnd.choice(("capcom", "crew")))
            place(L, R, msg, t, 0.35, rnd.uniform(-0.4, 0.4))
            end = t + len(msg) / RATE
            if rnd.random() < 0.4:                      # keep typing while listening
                typing(t + rnd.uniform(0.8, 1.5), end - 0.3)
            t = end + rnd.uniform(0.5, 1.5)
            last = "radio"
        elif pick == "data":                           # data squealing in
            d = rnd.uniform(0.6, 1.8)
            place(L, R, data_burst(rnd, d), t, 0.1, rnd.uniform(-0.5, 0.5))
            t += d + rnd.uniform(0.4, 1.2)
            last = "data"
        else:                                           # a satellite beacon passing over
            pan, d = rnd.uniform(-0.6, 0.6), rnd.uniform(5, 8)
            hz, s = rnd.uniform(880, 1050), 0.0
            while s < d and t + s < LOOP - 1:
                place(L, R, tone(hz, 0.3, 0.01), t + s, 0.06 * sin(pi * s / d), pan)
                s += 0.6
            t += rnd.uniform(1.5, 3)                    # typing carries on under it
            last = "beacon"
    return L, R


def clacky_key(rnd, weight=1.0, up=False):
    """A smooth, creamy mechanical key: a rounded 'clack' from the keycap
    ringing (pure tones, no gritty noise), a warm thock as it bottoms out,
    and a softer, higher clack when it comes back up. Bigger keys (weight > 1)
    sound deeper and last a little longer."""
    n = sec(0.06)
    lift = 1.12 if up else 1.0
    modes = [(rnd.uniform(1700, 2300) * lift / weight ** 0.5, 1.0, 0.007),   # the clack
             (rnd.uniform(2900, 3700) * lift / weight ** 0.5, 0.45, 0.004),
             (rnd.uniform(4600, 5400) * lift, 0.15, 0.002)]
    if not up:
        modes.append((rnd.uniform(380, 480) / weight, 1.3 * weight, 0.016 * weight))   # the thock
    out = [0.0] * n
    for hz, amp, decay in modes:
        w, d, ph = TAU * hz / RATE, decay * RATE, rnd.uniform(0, TAU)
        for k in range(n):
            out[k] += amp * sin(ph + w * k * (1 - 0.04 * k / n)) * exp(-k / d)
    attack = sec(0.0007)                       # round off the very start: smooth, not sharp
    for k in range(attack):
        out[k] *= k / attack
    return [v * (0.35 if up else 1.0) for v in out]


def bell(hz, ring=1.6):
    """A glassy 'ding': a few bell-like overtones fading at different speeds."""
    n = sec(ring * 2.5)
    out = [0.0] * n
    for mult, amp, decay in ((1.0, 1.0, 1.0), (2.76, 0.35, 0.45), (5.4, 0.12, 0.2), (2.0, 0.2, 0.7)):
        w = TAU * hz * mult / RATE
        d = ring * decay * RATE
        for k in range(n):
            out[k] += amp * sin(w * k) * exp(-k / d)
    for k in range(min(n, 60)):                # no click at the start
        out[k] *= k / 60
    return out


def whistler(rnd):
    """A 'whistler': lightning's radio crackle stretched by the magnetosphere
    into a falling whistle (it's real, and sounds like a sci-fi slide)."""
    d = rnd.uniform(1.2, 2.2)
    top, bottom = rnd.uniform(3500, 5500), rnd.uniform(500, 900)
    n, ph, out = sec(d), 0.0, []
    for k in range(n):
        q = k / n
        f = bottom + (top - bottom) / (1 + 7 * q) ** 2
        ph += TAU * f / RATE
        out.append(sin(ph) * min(1.0, q * 25) * (1 - q) ** 1.5)
    return out


def chorus(rnd):
    """'Chorus': quick rising chirps from Earth's radiation belts, like a
    flock of far-off birds."""
    out = []
    for _ in range(rnd.randint(4, 9)):
        d = rnd.uniform(0.12, 0.3)
        lo = rnd.uniform(700, 1100)
        hi = lo * rnd.uniform(1.6, 2.3)
        n, ph = sec(d), 0.0
        for k in range(n):
            q = k / n
            ph += TAU * (lo + (hi - lo) * q * q) / RATE
            out.append(sin(ph) * sin(pi * q) ** 2)
        out += silence(rnd.uniform(0.05, 0.35))
    return out


def echo(L, R, left=0.31, right=0.47, feedback=0.42):
    """A ping-pong echo, so sounds ring out across a big, empty space (in place)."""
    a, b = sec(left), sec(right)
    for i in range(N):
        if i >= a:
            L[i] += feedback * R[i - a]
        if i >= b:
            R[i] += feedback * L[i - b]


def make_observatory(rnd):
    """A quiet observatory at night: a soft drone, someone typing gently,
    glassy dings, and the whistles and chirps of space weather on the radio."""
    # the drone: a calm, open chord whose notes slowly swell in and out, with
    # only a breath of noise underneath
    L = [0.0] * N
    R = [0.0] * N
    for hz, amp, period, side in ((110.0, 0.5, 23, 0), (110.3, 0.35, 31, 1), (164.81, 0.3, 19, 0),
                                  (220.0, 0.2, 29, 1), (277.18, 0.08, 37, 0), (329.63, 0.1, 17, 1)):
        w = TAU * hz / RATE
        ph = rnd.uniform(0, TAU)
        chan, other = (L, R) if side == 0 else (R, L)
        for b in range(0, N, 256):
            g = amp * (0.5 + 0.5 * sin(TAU * b / RATE / period + ph))
            for i in range(b, min(N, b + 256)):
                v = g * sin(ph + w * i)
                chan[i] += v
                other[i] += 0.6 * v
    air = lowpass(brown(white(rnd)), 400)
    air2 = shifted(air)
    for i in range(N):
        L[i] = 0.1 * L[i] + 0.15 * air[i]
        R[i] = 0.1 * R[i] + 0.15 * air2[i]

    # sounds that ring out through the echo: dings, whistlers, chorus
    fxL, fxR = [0.0] * N, [0.0] * N
    notes = (659.26, 783.99, 880.0, 987.77, 1174.66, 1318.51)      # a soft pentatonic
    t = FADE + rnd.uniform(1, 4)
    while t < LOOP - 4:
        hz = rnd.choice(notes)
        place(fxL, fxR, bell(hz), t, 0.09, rnd.uniform(-0.6, 0.6))
        if rnd.random() < 0.35:                               # a two-note ding
            place(fxL, fxR, bell(hz * 1.5), t + 0.18, 0.06, rnd.uniform(-0.6, 0.6))
        t += rnd.uniform(7, 14)
    for t in (rnd.uniform(9, 16), rnd.uniform(28, 34), rnd.uniform(45, 52)):
        place(fxL, fxR, whistler(rnd), t, 0.05, rnd.uniform(-0.8, 0.8))
    for t in (rnd.uniform(18, 24), rnd.uniform(38, 43)):
        place(fxL, fxR, chorus(rnd), t, 0.04, rnd.uniform(-0.7, 0.7))
    echo(fxL, fxR)
    for i in range(N):
        L[i] += fxL[i]
        R[i] += fxR[i]

    # smooth, clacky typing, dry and close, flowing along in stretches
    keys = [clacky_key(rnd) for _ in range(10)]
    ups = [clacky_key(rnd, up=True) for _ in range(5)]
    space = [clacky_key(rnd, 1.6) for _ in range(2)]
    space_up = clacky_key(rnd, 1.6, up=True)

    def press(sound, up, t, gain):
        pan = rnd.uniform(-0.15, 0.25)
        place(L, R, sound, t, gain * rnd.uniform(0.85, 1.0), pan)
        place(L, R, up, t + rnd.uniform(0.07, 0.1), gain, pan)

    t = FADE + rnd.uniform(0.5, 2)
    while t < LOOP - 3:
        until = min(LOOP - 2, t + rnd.uniform(3, 8))
        while t < until:
            for _ in range(rnd.randint(2, 7)):
                press(rnd.choice(keys), rnd.choice(ups), t, 0.1)
                t += max(0.1, rnd.gauss(0.15, 0.022))      # an even, flowing rhythm
            press(rnd.choice(space), space_up, t, 0.11)
            t += max(0.14, rnd.gauss(0.19, 0.03))
            if rnd.random() < 0.1:
                t += rnd.uniform(0.6, 1.6)
        t += rnd.uniform(3, 8)                                # sit back and think
    return L, R


def make_station(rnd):
    """Inside a space station: the steady roar of cabin fans, humming
    equipment, a pump now and then, soft chimes and a far-off radio call."""
    w = white(rnd)
    fan = [a + 0.12 * b for a, b in zip(lowpass(pink(w), 2200), highpass(shifted(w), 3500))]
    L, R = fan, shifted(fan)
    hum = [0.0] * N
    for hz, a in ((118, 0.05), (236, 0.025), (354, 0.012), (59.2, 0.03)):
        step = TAU * hz / RATE
        for i in range(N):
            hum[i] += a * sin(step * i)
    for i in range(N):
        L[i] += hum[i]
        R[i] += hum[i]

    t = FADE + rnd.uniform(3, 8)            # pumps whirring up and down
    while t < LOOP - 7:
        d = rnd.uniform(4, 6)
        whir = biquad(white(rnd, sec(d)), "bp", rnd.uniform(280, 520), 6)
        whir = [v * sin(pi * k / len(whir)) ** 2 for k, v in enumerate(whir)]
        place(L, R, whir, t, 2.5, rnd.uniform(-0.8, 0.8))
        t += rnd.uniform(14, 24)

    t = FADE + rnd.uniform(1, 5)            # equipment chimes
    while t < LOOP - 2:
        chime = (tone(1318.5, 0.5, 0.01, 0.12) + silence(0.02))
        chime += tone(1760, 0.8, 0.01, 0.2)
        place(L, R, chime, t, 0.22, rnd.uniform(-0.7, 0.7))
        t += rnd.uniform(11, 21)

    for t in (rnd.uniform(9, 14), rnd.uniform(34, 40)):   # a call from the ground, down the hall
        call = lowpass(transmission(rnd, rnd.choice(("capcom", "crew"))), 1800)
        place(L, R, call, t, 0.5, rnd.uniform(-0.5, 0.5))
    return L, R


def make_mission(rnd):
    """Mission control: back-and-forth radio between the ground and a crew,
    with Quindar beeps, crackle, squelch and the murmur of the room."""
    w = white(rnd)
    room = [a + 0.5 * b for a, b in zip(lowpass(pink(w), 1300), brown(shifted(w)))]
    L, R = room, shifted(room)
    for i in range(N):
        L[i] *= 0.6
        R[i] *= 0.6

    for k in range(4):                      # other consoles talking quietly
        murmur = lowpass(babble(rnd, rnd.uniform(3, 6), rnd.uniform(100, 200)), 900)
        place(L, R, normalize(murmur), rnd.uniform(FADE, LOOP - 7), 0.05, rnd.choice((-0.9, 0.9)))

    t = FADE + rnd.uniform(0.5, 2)
    while t < LOOP - 6:
        msg = transmission(rnd, "capcom")
        place(L, R, msg, t, 0.55, -0.25)
        t += len(msg) / RATE + rnd.uniform(0.7, 1.6)
        if t >= LOOP - 6:
            break
        msg = transmission(rnd, "crew")
        place(L, R, msg, t, 0.55, 0.25)
        t += len(msg) / RATE + rnd.uniform(3.5, 8)
        if rnd.random() < 0.6 and t < LOOP - 3:      # telemetry ping
            ping = tone(1200, 0.07) + silence(0.09) + tone(1200, 0.07)
            place(L, R, ping, t - rnd.uniform(1, 2.5), 0.06, 0.6)
    return L, R


def make_shortwave(rnd):
    """Tuning across the shortwave band: static that fades in and out, morse
    code, whistles from neighbouring stations and the steady tick of a pulsar."""
    x = biquad(biquad(white(rnd), "lp", 3000), "hp", 180)
    fading = lambda t: 0.45 + 0.55 * slow(t, (7, 0.3), (19, 2.0), (3.1, 1.1))
    L, R = envelope(x, fading), shifted(x)
    envelope(R, lambda t: 0.85 + 0.15 * slow(t, (5, 1)))
    for ch in (L, R):
        crackle(rnd, ch, FADE, LOOP, rate=7, gain=0.8)

    for t in (rnd.uniform(6, 9), rnd.uniform(30, 36)):        # morse code
        hz, wpm = rnd.uniform(600, 820), rnd.uniform(14, 20)
        cs = callsign(rnd)
        cw = morse(f"CQ CQ DE {cs} {cs} K", hz, wpm)
        cw = cw[:sec(LOOP - 1 - t)]
        cw = envelope(cw, lambda s: 0.5 + 0.5 * slow(s, (4, 0.0)))
        place(L, R, cw, t, 0.2, rnd.uniform(-0.3, 0.3))

    for t in (rnd.uniform(15, 20), rnd.uniform(44, 50)):      # heterodyne whistles
        d = rnd.uniform(3, 5)
        f0, f1 = rnd.uniform(300, 900), rnd.uniform(900, 2200)
        n, ph, wh = sec(d), 0.0, []
        for k in range(n):
            q = k / n
            ph += TAU * (f0 + (f1 - f0) * q + 15 * sin(TAU * q * 3)) / RATE
            wh.append(sin(ph) * sin(pi * q) ** 2)
        place(L, R, wh, t, 0.2, rnd.uniform(-0.5, 0.5))

    t, end = rnd.uniform(22, 26), rnd.uniform(40, 43)        # a pulsar, ticking every 0.714 s
    while t < end:
        n = sec(0.05)
        thump = lowpass([(rnd.random() * 2 - 1) * exp(-k / (0.012 * RATE)) for k in range(n)], 900)
        swell = sin(pi * min(1.0, (t - 22) / 18))
        place(L, R, thump, t, 2.2 * swell * rnd.uniform(0.5, 1.0), 0.0)
        t += 0.714
    return L, R


# slug: (title, maker, how loud it should be, what it is). Deeper sounds need
# more level to seem as loud as bright ones.
TRACKS = {
    "static": ("cosmic static", make_static, 0.085, "soft, even white noise"),
    "deepspace": ("deep space", make_deepspace, 0.2, "low brown noise, slowly breathing"),
    "console": ("comms console", make_console, 0.12, "typing, radio calls and data signals"),
    "observatory": ("observatory", make_observatory, 0.1, "soft typing, glassy dings and space whistles"),
    "station": ("space station", make_station, 0.12, "cabin fans, chimes and a far-off radio call"),
    "mission": ("mission control", make_mission, 0.12, "radio chatter, Quindar beeps and squelch"),
    "shortwave": ("shortwave", make_shortwave, 0.11, "static, morse code, whistles and a pulsar"),
}
NAMES = list(TRACKS)


# ---------------------------------------------------------------- making the files

def cache_dir():
    base = os.path.expanduser("~/Library/Caches")
    if not os.path.isdir(base):
        base = tempfile.gettempdir()
    folder = os.path.join(base, "ascii_pomodoro")
    os.makedirs(folder, exist_ok=True)
    return folder


def cache_path(slug):
    return os.path.join(cache_dir(), f"{slug}_v{VERSION}.wav")


def make(slug, path=None):
    """Work out one track and save it as a stereo .wav file."""
    path = path or cache_path(slug)
    title, maker, loudness, _ = TRACKS[slug]
    rnd = random.Random(slug)
    L, R = maker(rnd)

    f = sec(FADE)                    # fade the ends so overlapping loops blend
    for k in range(f):
        g = sin(0.5 * pi * k / f)
        for ch in (L, R):
            ch[k] *= g
            ch[N - 1 - k] *= g
    # match the loudness between tracks, then round off any peaks gently
    rms = math.sqrt(sum(v * v for v in L[f:-f]) / (N - 2 * f) / 2
                    + sum(v * v for v in R[f:-f]) / (N - 2 * f) / 2)
    k = loudness / max(rms, 1e-9)

    def sample(v):
        v *= k
        if v > 0.7:
            v = 0.7 + 0.29 * tanh((v - 0.7) / 0.29)
        elif v < -0.7:
            v = -0.7 - 0.29 * tanh((-v - 0.7) / 0.29)
        return int(v * 32767)

    data = array.array("h", bytes(4 * N))
    data[0::2] = array.array("h", map(sample, L))
    data[1::2] = array.array("h", map(sample, R))

    tmp = f"{path}.{os.getpid()}.part"
    with wave.open(tmp, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(data.tobytes())
    os.replace(tmp, path)
    _tidy()


def _tidy():
    """Remove sound files left over from older versions."""
    keep = {os.path.basename(cache_path(s)) for s in TRACKS}
    folder = cache_dir()
    for name in os.listdir(folder):
        if name.endswith(".wav") and name not in keep:
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass


_locks = {slug: threading.Lock() for slug in TRACKS}


def ensure(slug, on_wait=None):
    """Make sure a track's file exists (making it in a separate process if
    needed, so it doesn't slow the animation down). Returns its path, or
    None if it couldn't be made."""
    path = cache_path(slug)
    with _locks[slug]:
        if not os.path.exists(path):
            if on_wait:
                on_wait()
            try:
                subprocess.run([sys.executable, os.path.abspath(__file__), "--make", slug],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
            except (OSError, subprocess.SubprocessError):
                pass
    return path if os.path.exists(path) else None


# ---------------------------------------------------------------- playing it

class Ambient:
    """Loops the current track in the background. toggle() switches it on and
    off, next_track() moves on to the next one; on_message(text) is called with
    anything worth showing."""

    def __init__(self, volume=0.5, track=None, on_message=None):
        self.volume = max(0.0, min(1.0, volume))
        self.track = NAMES.index(track) if track in TRACKS else 0
        self.on = False
        self.on_message = on_message or (lambda msg: None)
        self.procs = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.run_id = 0

    @property
    def slug(self):
        return NAMES[self.track]

    @property
    def title(self):
        return TRACKS[self.slug][0]

    def toggle(self):
        if self.on:
            self.stop()
        else:
            self.start()
        return self.on

    def next_track(self, step=1):
        """Switch to the next track (and start playing if it was off)."""
        self.track = (self.track + step) % len(NAMES)
        self.stop()
        self.start()
        return self.title

    def start(self):
        if self.on:
            return
        self.on = True
        self.run_id += 1
        self.wake = threading.Event()
        threading.Thread(target=self._loop, args=(self.run_id, self.wake, self.slug),
                         daemon=True).start()

    def stop(self):
        self.on = False
        self.wake.set()
        with self.lock:
            for p in self.procs:
                if p.poll() is None:
                    p.terminate()
            self.procs = []

    def _current(self, run_id):
        return self.on and run_id == self.run_id

    def _loop(self, run_id, wake, slug):
        title = TRACKS[slug][0]
        path = ensure(slug, lambda: self._current(run_id)
                      and self.on_message(f"tuning in to {title}…"))
        if not self._current(run_id):
            return
        if path is None:
            self.on_message("couldn't make the space sounds")
            self.on = False
            return
        upcoming = NAMES[(NAMES.index(slug) + 1) % len(NAMES)]
        threading.Thread(target=ensure, args=(upcoming,), daemon=True).start()  # get ahead
        while self._current(run_id):
            try:
                p = subprocess.Popen(["afplay", "-v", f"{self.volume:.2f}", path],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                self.on_message("sound needs afplay (it comes with macOS)")
                self.on = False
                return
            with self.lock:
                if not self._current(run_id):      # switched off meanwhile
                    p.terminate()
                    return
                self.procs = [q for q in self.procs if q.poll() is None] + [p]
            if wake.wait(LOOP):
                return


# ---------------------------------------------------------------- command line

def _main(args):
    if args[:1] == ["--make"] and len(args) == 2:
        try:
            os.nice(8)                   # stay out of the way of the animation
        except OSError:
            pass
        for slug in (NAMES if args[1] == "all" else [args[1]]):
            if slug not in TRACKS:
                sys.exit(f"no track called {slug!r}")
            make(slug)
        return
    if len(args) == 1 and args[0] in TRACKS:
        path = cache_path(args[0])
        if not os.path.exists(path):
            print(f"making {TRACKS[args[0]][0]}…")
            make(args[0])
        print(f"playing one loop of {TRACKS[args[0]][0]} (ctrl+c to stop)")
        try:
            subprocess.run(["afplay", path])
        except KeyboardInterrupt:
            pass
        return
    for slug, (title, _, _, blurb) in TRACKS.items():
        print(f"  {slug:<12} {title:<16} {blurb}")
    print("\nplay one with: python3 sound.py <name>")


if __name__ == "__main__":
    _main(sys.argv[1:])
