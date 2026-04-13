"""
Eye Tracking Calibration – Ingescape agent
==========================================
Displays images/FixationCrossDemo.jpeg fullscreen on every connected screen
with a screen number (1-N) in the top-left corner.

Impulsion input  'toggle_calibration':
  - First trigger  → open fullscreen windows on all screens
  - Second trigger → destroy all windows, keep waiting

Usage:
  python eye_tracking_calibration.py
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import tkinter as tk
from PIL import Image, ImageTk
from screeninfo import get_monitors
import ingescape as igs

# ── Configuration ────────────────────────────────────────────────
IGS_PORT   = 5670
IGS_AGENT  = "EyeTrackingCalibration_TARS"
IGS_DEVICE = "Wi-Fi"
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "images", "FixationCrossDemo.jpeg")

# ── State ────────────────────────────────────────────────────────
_toggle_event: threading.Event = threading.Event()   # set by Ingescape callback
_windows: list[tk.Toplevel] = []
_windows_open: bool = False
_photo_refs: list[ImageTk.PhotoImage] = []           # prevent GC


# ── Ingescape callback (runs in Ingescape thread) ────────────────
def on_toggle_calibration(igs_type, name, value_type, value, my_data) -> None:
    """Signal the main (Tkinter) thread to open or close windows."""
    _toggle_event.set()


# ── Window management (runs in main/Tkinter thread) ──────────────
def _open_windows(root: tk.Tk) -> None:
    global _windows, _windows_open, _photo_refs

    monitors = get_monitors()
    _photo_refs.clear()

    for i, m in enumerate(monitors, start=1):
        win = tk.Toplevel(root)
        win.overrideredirect(True)          # no title bar / chrome
        win.configure(bg="black")
        win.geometry(f"{m.width}x{m.height}+{m.x}+{m.y}")
        win.lift()
        win.attributes("-topmost", True)

        # Load and scale image to fill this monitor
        img = Image.open(IMAGE_PATH).resize((m.width, m.height), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        _photo_refs.append(photo)           # keep reference alive

        canvas = tk.Canvas(
            win, width=m.width, height=m.height,
            bg="black", highlightthickness=0
        )
        canvas.pack(fill="both", expand=True)
        canvas.create_image(0, 0, anchor="nw", image=photo)

        # Screen number — top-left, large white bold text
        canvas.create_text(
            20, 20, text="TARS",
            fill="white", font=("Arial", 64, "bold"),
            anchor="nw"
        )

        _windows.append(win)

    _windows_open = True
    print(f"[CAL] Opened calibration image on {len(monitors)} screen(s)")


def _close_windows() -> None:
    global _windows, _windows_open, _photo_refs

    for win in _windows:
        try:
            win.destroy()
        except tk.TclError:
            pass
    _windows.clear()
    _photo_refs.clear()
    _windows_open = False
    print("[CAL] Calibration windows closed")


def _poll_toggle(root: tk.Tk) -> None:
    """Called every 100 ms by Tkinter's event loop to check for a toggle."""
    global _windows_open

    if _toggle_event.is_set():
        _toggle_event.clear()
        if _windows_open:
            _close_windows()
        else:
            _open_windows(root)

    root.after(100, _poll_toggle, root)


# ── Entry point ──────────────────────────────────────────────────
def main() -> None:
    # Hidden root window – just drives the Tkinter event loop
    root = tk.Tk()
    root.withdraw()

    # ── Initialize Ingescape ─────────────────────────────────────
    igs.agent_set_name(IGS_AGENT)
    igs.input_create("toggle_calibration", igs.IMPULSION_T, None)
    igs.observe_input("toggle_calibration", on_toggle_calibration, None)
    igs.log_set_console(True)
    igs.log_set_console_level(igs.LOG_INFO)
    igs.start_with_device(IGS_DEVICE, IGS_PORT)

    # Graceful Ctrl+C → destroy root, which exits mainloop
    def _sigint_handler(sig, frame):
        print("\n[CAL] Interrupted, shutting down...")
        root.destroy()

    signal.signal(signal.SIGINT, _sigint_handler)

    print(f"[OK] Ingescape agent '{IGS_AGENT}' started on {IGS_DEVICE}:{IGS_PORT}")
    print("[CAL] Waiting for toggle_calibration impulsion... (Ctrl+C to quit)\n")

    # Start polling loop and hand control to Tkinter
    root.after(100, _poll_toggle, root)
    root.mainloop()

    # ── Cleanup ──────────────────────────────────────────────────
    igs.stop()
    igs.clear_definition()
    print("[CAL] Agent stopped.")


if __name__ == "__main__":
    main()
