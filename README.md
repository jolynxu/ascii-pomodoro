# ascii-pomodoro

a pomodoro timer for the mac terminal, except you're floating in space.

pick from 10 animated backgrounds (black holes, comets, eclipses, all that),
and while you're in a focus session it'll quietly close discord and whatever
else you'd otherwise end up on. it also shows what's playing on spotify so you
don't have to leave the terminal to skip a song.

## running it

```bash
python3 ascii_pomodoro.py
```

no installs, just python 3. some other ways to start it:

```bash
python3 ascii_pomodoro.py --focus 50 --break 10    # longer sessions, just for this run
python3 ascii_pomodoro.py --scene comet            # start on a specific background
python3 ascii_pomodoro.py --focus 0.2 --break 0.1  # 12s focus / 6s break, good for testing
```

## the backgrounds

flip through them with the arrow keys, or press the number to jump straight there.

| key | name        | what it is                                                     |
|-----|-------------|----------------------------------------------------------------|
| 1   | `planet`    | ringed gas giant, a little moon going round it                 |
| 2   | `nebula`    | pink and teal gas clouds with baby stars blinking inside       |
| 3   | `blackhole` | black hole eating a glowing disk of gas                        |
| 4   | `warp`      | stars streaking past at warp speed (it jumps every so often)   |
| 5   | `galaxy`    | spiral galaxy, slowly turning                                  |
| 6   | `sun`       | the surface of a star, with flares looping off the edge        |
| 7   | `orbit`     | earth from orbit: city lights, aurora, a satellite floats by   |
| 8   | `pulsar`    | spinning neutron star sweeping its beams around like a lighthouse |
| 9   | `comet`     | comet with a blue ion tail and a dusty gold one                |
| 0   | `eclipse`   | total solar eclipse, with a diamond ring flash now and then    |

keep an eye out on `orbit`: a train of satellites crosses the sky every so
often, and the big satellite flashes when the sun catches its panels.

**if the colors look weird or blocky**, press `c` to switch to 256-color mode (or
start with `--colors 256`). the glow needs a terminal with 24-bit color.
Terminal on macOS 26+, iTerm2, Ghostty and the VS Code terminal all have it.
if it feels laggy, `g` turns the glow off.

## keys

**timer**

- `space` start / pause
- `s` skip to the next session
- `r` restart the current session
- `q` quit

**backgrounds**

- `←` `→` (or `[` `]`) previous / next
- `1`–`9`, `0` jump to one
- `g` glow on / off
- `c` switch between 24-bit and 256 colors

**spotify**

- `p` play / pause
- `n` next song
- `b` previous song

the row of dots under the timer is your progress toward a long break. finished
sessions light up, the one you're on fills in as time goes by, and the little
star at the end lights up when you've earned the long break.

## settings

everything lives in `config.json`:

| setting                      | what it does                                     |
|------------------------------|--------------------------------------------------|
| `scene`                      | which background to start on                     |
| `focus_minutes`              | how long a focus session is                      |
| `short_break_minutes`        | how long a short break is                        |
| `long_break_minutes`         | how long a long break is                         |
| `sessions_before_long_break` | focus sessions before you get a long break       |
| `auto_start_breaks`          | start the break right away when focus ends       |
| `auto_start_focus`           | start focusing right away when a break ends      |
| `blocklist`                  | apps that get closed while you're focusing       |

### the blocklist

you can edit it while the timer's running. it picks up changes when you save.

names have to match what's in the Dock. if you're not sure what an app is
called, this prints everything you have open:

```bash
osascript -e 'tell application "System Events" to get displayed name of every application process whose background only is false'
```

apps get asked to quit normally (like pressing ⌘Q), so if you have unsaved
work they'll still ask before closing. Finder, Terminal, iTerm2 and VS Code are
never closed, even if you put them on the list by accident.

## first run: permission popups

the first time you run it, macOS will ask things like *"Terminal wants access to
control System Events"* or *"...to control Discord"*. click **OK** / **Allow** on
all of them, otherwise the blocklist and spotify stuff won't work.

hit **Don't Allow** by accident? go to **System Settings → Privacy & Security →
Automation**, find your terminal app, and turn them back on.

## spotify

talks to the spotify desktop app through AppleScript, so you don't need an api
key, a login or premium. if spotify's open, the current song shows at the
bottom. it won't ever open spotify for you.
