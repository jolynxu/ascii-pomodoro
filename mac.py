"""Talking to macOS: running apps, quitting apps, notifications and Spotify.

Everything here goes through `osascript` (AppleScript), which comes with
every Mac. If a call fails (no permission yet, or not on a Mac), the
functions return None or False instead of crashing the timer.
"""

import subprocess

# Apps the timer will never quit, even if they end up on the blocklist.
PROTECTED = {"finder", "terminal", "iterm2", "code", "visual studio code",
             "system settings", "system preferences", "dock", "loginwindow"}

last_error = None  # a short message the timer can show on screen


def _osascript(script, timeout=3):
    """Run an AppleScript and return its output, or None if it failed."""
    global last_error
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True,
                                text=True, timeout=timeout)
    except FileNotFoundError:
        last_error = "osascript not found (this part only works on a Mac)"
        return None
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        if "not allowed" in result.stderr or "-1743" in result.stderr:
            last_error = ("Allow your terminal under System Settings > "
                          "Privacy & Security > Automation")
        return None
    last_error = None
    return result.stdout.strip()


# ------------------------------------------------------------ apps

def running_apps():
    """Names of the apps open in the Dock, e.g. ['Finder', 'Discord']."""
    out = _osascript('tell application "System Events" to get displayed name '
                     'of every application process whose background only is false')
    if out is None:
        return None
    return [name.strip() for name in out.split(",") if name.strip()]


def quit_app(name):
    """Ask an app to quit normally (it can still ask you to save your work)."""
    if name.lower() in PROTECTED:
        return False
    safe = name.replace('"', '\\"')
    return _osascript(f'tell application "{safe}" to quit') is not None


# ------------------------------------------------------------ full screen

def _window_script(body):
    return ('tell application "System Events"\n'
            '  tell front window of (first application process whose frontmost is true)\n'
            f'    {body}\n'
            '  end tell\n'
            'end tell')


def _run_fullscreen_script(script):
    """Returns the script's output, or an error message prefixed with '!'."""
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True,
                                text=True, timeout=3)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "!full screen only works on a mac"
    if result.returncode != 0:
        if "assistive" in result.stderr or "-25211" in result.stderr or "-1719" in result.stderr:
            return ("!full screen needs your terminal turned on in System Settings > "
                    "Privacy & Security > Accessibility")
        return "!couldn't switch full screen (try ctrl+cmd+f)"
    return result.stdout.strip()


def is_fullscreen():
    """Is the frontmost window (your terminal) in full screen? True/False, or
    an error message string."""
    out = _run_fullscreen_script(_window_script(
        'return (value of attribute "AXFullScreen") as string'))
    return out[1:] if out.startswith("!") else out == "true"


def set_fullscreen(on):
    """Put the frontmost window in (on=True) or out of (on=False) full screen.
    Returns None if it worked, or an error message string."""
    out = _run_fullscreen_script(_window_script(
        f'set value of attribute "AXFullScreen" to {"true" if on else "false"}'))
    return out[1:] if out.startswith("!") else None


# ------------------------------------------------------------ window padding color
# Terminal.app leaves a few pixels of padding around the text grid, painted in
# the profile's background color. Matching it to the scene's edges hides the
# "border". Other terminals understand the standard OSC 11 escape code instead,
# which the timer writes itself.

def _tab_script(tty, body):
    return ('tell application "Terminal"\n'
            '  repeat with w in windows\n'
            '    repeat with t in tabs of w\n'
            f'      if tty of t is "{tty}" then\n'
            f'        {body}\n'
            '      end if\n'
            '    end repeat\n'
            '  end repeat\n'
            'end tell')


def get_tab_background(tty):
    """The Terminal.app tab's background as an AppleScript color, e.g. '0, 0, 0'."""
    try:
        result = subprocess.run(["osascript", "-e", _tab_script(
            tty, "return background color of t")], capture_output=True, text=True, timeout=3)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    out = result.stdout.strip()
    return out if result.returncode == 0 and out.count(",") == 2 else None


def set_tab_background(tty, color):
    """color is (r, g, b) 0-255, or a string returned by get_tab_background."""
    if not isinstance(color, str):
        color = ", ".join(str(int(max(0, min(255, c))) * 257) for c in color)
    try:
        subprocess.run(["osascript", "-e", _tab_script(
            tty, "set background color of t to {" + color + "}\n        return")],
            capture_output=True, timeout=3)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


# ------------------------------------------------------------ alerts

def notify(title, message):
    """Show a macOS notification and play a sound."""
    _osascript(f'display notification "{message}" with title "{title}"')
    try:
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


# ------------------------------------------------------------ spotify

def spotify_now_playing():
    """Return (state, track, artist) from the Spotify app, or None."""
    out = _osascript(
        'tell application "Spotify"\n'
        '  set s to player state as string\n'
        '  set n to name of current track\n'
        '  set a to artist of current track\n'
        '  return s & "|" & n & "|" & a\n'
        'end tell')
    if not out or out.count("|") < 2:
        return None
    state, track, artist = out.split("|", 2)
    return state, track, artist


def spotify_command(command):
    """command is one of: 'playpause', 'next track', 'previous track'."""
    _osascript(f'tell application "Spotify" to {command}')
