# ascii-pomodoro

A space-themed pomodoro timer for the macOS terminal. While a focus session
is running, it quits distracting apps from your blocklist. It also shows
what's playing in Spotify and lets you control it with your keyboard.

## Run

```bash
python3 ascii_pomodoro.py
```

Change the session lengths for one run:

```bash
python3 ascii_pomodoro.py --focus 50 --break 10
python3 ascii_pomodoro.py --focus 0.2 --break 0.1   # quick test: 12s focus, 6s break
```

## Keys

| Key     | Does                       |
|---------|----------------------------|
| `space` | start / pause              |
| `s`     | skip to the next session   |
| `r`     | restart the current session|
| `p`     | Spotify play / pause       |
| `n`     | Spotify next song          |
| `b`     | Spotify previous song      |
| `q`     | quit                       |

## Settings (`config.json`)

| Setting                      | What it does                                         |
|------------------------------|------------------------------------------------------|
| `focus_minutes`              | Length of a focus session                            |
| `short_break_minutes`        | Length of a short break                              |
| `long_break_minutes`         | Length of a long break                               |
| `sessions_before_long_break` | Focus sessions before a long break                   |
| `auto_start_breaks`          | Start breaks automatically when focus ends           |
| `auto_start_focus`           | Start focus automatically when a break ends          |
| `blocklist`                  | Apps to quit while a focus session is running        |

You can edit the blocklist while the timer is running. It reloads on save.

Use each app's name as it appears in the Dock. To see the exact names of
everything you have open, run:

```bash
osascript -e 'tell application "System Events" to get displayed name of every application process whose background only is false'
```

Blocked apps are asked to quit normally, so they can still ask you to save
your work. Finder, Terminal, iTerm2 and VS Code are never quit.

## First-run permissions

macOS asks before one app can control another. The first time you run the
timer, you'll see pop-ups like "Terminal wants access to control System
Events" or "...to control Discord". Click **OK** or **Allow** for each one.

If you clicked **Don't Allow** by mistake, turn it back on in
**System Settings → Privacy & Security → Automation**, under your terminal app.

## Spotify

The timer talks to the Spotify desktop app on your Mac through AppleScript.
No API key, login or Premium needed. Open Spotify and the current song
appears at the bottom of the screen. The timer never opens Spotify by itself.

