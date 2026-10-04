# Raspberry Pi as the main screen

The Pi replaces the laptop. It shows the game UI on its own display, reads the OGs and the camera over USB, and (later) uploads round summaries. Nothing here has been run on a Pi yet: every step below is a plan to check, not a result.

```
HDMI display <- Raspberry Pi 5 -- USB --> OG #1 (controller)
                    |            -- USB --> OG #2 (controller)
                    +------------ USB --> webcam (face numbers)
```

The OGs are flashed from the laptop as before (`python tools\fw.py build/flash orca_main`). The Pi never flashes them.

## 1. Set up the Pi without touching what is already there

Everything goes in one new folder with its own Python environment. Nothing is installed system-wide with pip, no existing folder or file is edited, and your current code keeps running as it is.

**Check first (changes nothing):**
```
python3 --version
python3 -c "import tkinter; print('tkinter ok')"
groups
```
- `tkinter ok` means you need no `apt` step at all. Skip the next block.
- If tkinter is missing, this is the only system change, and it only adds a package: `sudo apt install -y python3-tk`. (apt can pull in newer versions of libraries it shares with other software, so if the existing code is fragile, take a backup or an SD card image first.)
- `groups` should list `dialout`. If it does not, the OG serial ports will not open; adding yourself is `sudo usermod -aG dialout $USER` then log out and in. That changes your user's groups, not any software.

**Make the new folder and a private environment:**
```
mkdir -p ~/orca_run
cd ~/orca_run
# copy the project in here (git clone, or a USB stick), so the path is ~/orca_run/wiliOGbsp
cd wiliOGbsp/orca/host
python3 -m venv .venv                 # a plain venv: it does NOT see the system's packages
source .venv/bin/activate
python -m pip install pyserial pytest pillow numpy opencv-python
```
- A plain venv means these installs stay inside `.venv` and cannot change the packages your existing code uses. Never use `sudo pip` or `--break-system-packages` here.
- Session logs and settings (`sessions/`, `og_settings.json`) are written relative to where you run the games, so they land in this folder too. Run everything from `orca/host`.
- To undo it all: delete `~/orca_run`.

**Two things that can still clash with your existing code (only while both run):**
- **The camera:** only one program can open it at a time. Stop the existing code before running `--face`.
- **The OG serial ports:** if the existing code opens the same OGs, only one program can hold each port.

## 2. Check the OGs are seen
Plug in one OG, then:
```
python -m serial.tools.list_ports -v
```
**Expect:** a `/dev/ttyACM...` entry with `VID:PID=093C:2055` (that is the display CPU). The games find it by this ID, so no port name is needed. Two OGs show two such entries.
**If nothing:** `groups` should list `dialout` (log out and in, or reboot, after adding it).

## 3. Check the camera
```
ls /dev/video*                        # the camera shows up as /dev/video0 (or higher)
python -c "import cv2; c=cv2.VideoCapture(0); print(c.isOpened()); c.release()"
```
**Expect:** `True`. If the webcam is not device 0, pass its number: `--face 1`.

## 4. Run
```
python -m pytest tests -q            # all pass, same as on the laptop
python -m orca.brick_break      # the OG should show the controller screen
python -m orca.brick_break --face     # with the webcam numbers (needs mediapipe, below)
```

## 5. Face numbers need mediapipe (the one uncertain part)
The pain-expression and heart-rate numbers use MediaPipe. A wheel for the Pi's ARM 64-bit Python may or may not exist for your Python version: try `python -m pip install mediapipe`. If it fails, the games still run; only `--face` is unavailable. Report the error and we decide (older Python, or run the face part on the laptop).

## What is not done yet
- **Two OGs in one game:** the games still use one OG. Supporting two is the next build step.
- **Fonts:** the UI asks for Segoe UI, which a Pi does not have, so Tk uses its default font. It works but looks a little different; a font fallback is a small change if you want it.
- **Full screen and auto-start on boot:** not set up.
- **Upload to Supabase:** the schema exists (`supabase_schema.sql`); the Pi-side uploader is not built.
- **OG shell mirror (`og_shell`):** it copies the screen with `ImageGrab`, which does not work on the Pi's Wayland desktop. The controller screens do not need it, so it is not part of the Pi plan.

## Power
The Pi 5 needs its own 5 V / 5 A supply. Two OGs and a webcam on its USB ports is within the port budget, but if a device drops out, use a powered USB hub.
