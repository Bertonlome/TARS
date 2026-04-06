#!/usr/bin/env python3
"""
Rudder Trim Agent - Standalone Ingescape Agent for autonomous rudder trimming.

Inputs:
  - start_trim   (IMPULSION_T): trigger to begin trimming towards slip == 0
  - slip         (DOUBLE_T):    current slip/skid value from the aircraft

Output:
  - trim_rudder  (DOUBLE_T):    rudder trim command (-1.0 to 1.0, can exceed limits programmatically)

The agent continuously adjusts trim_rudder until the slip value is centred
(|slip| < SLIP_SKID_THRESHOLD) and the internal rudder control is not being
actively applied (|control_rudder| < RUDDER_RELEASE_THRESHOLD).  It mirrors
the logic that previously lived in TarsAgent._trim_worker() but runs as an
independent OS process so that GIL contention, debugger pauses or GUI thread
pressure cannot interrupt the loop.
"""

import signal
import sys
import time
import threading
from pathlib import Path

# Add project root to sys.path so Core.igs_utils is importable
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import ingescape as igs
from Core.igs_utils import start_with_device_fallback

# ──────────────────────────────────────────────
# Tuning constants (mirror values in agent.py)
# ──────────────────────────────────────────────
SLIP_SKID_THRESHOLD = 1.0       # |slip| below this → "centred"
RUDDER_RELEASE_THRESHOLD = 0.15  # |control_rudder| below this → "released"
TRIM_STEP = 0.1                  # How much trim to add per loop iteration
TRIM_MAX = 5.0                   # Safety clamp on absolute trim value
LOOP_INTERVAL = 0.5              # Seconds between iterations
STABILITY_REQUIRED = 3.0         # Seconds of stability before announcing done


class RudderTrimAgent:
    """
    Self-contained rudder trim agent.

    State machine:
      IDLE  →  (start_trim received)  →  TRIMMING  →  (slip centred & stable)  →  MONITORING
      At any point: stop_trim received → IDLE
    """

    def __init__(self):
        # Live values updated by Ingescape callbacks
        self.slip: float = 0.0
        self.control_rudder: float = 0.0
        self.current_trim: float = 0.0   # shadow of our own last output

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._trim_thread: threading.Thread | None = None

        self._running = False

    # ──────────────────────────────────────────
    # Ingescape input callbacks
    # ──────────────────────────────────────────

    def on_start_trim(self, ioType, name, valueType, value, myData):
        """Impulsion received: begin (or restart) the trim loop."""
        print("🎚️  start_trim received — launching trim loop")
        self._launch_trim_thread()

    def on_stop_trim(self, ioType, name, valueType, value, myData):
        """Impulsion received: stop the trim loop."""
        print("🛑  stop_trim received — halting trim loop")
        self._stop_trim_thread()

    def on_slip(self, ioType, name, valueType, value, myData):
        """Updated slip/skid value from the aircraft."""
        if value is not None:
            with self._lock:
                self.slip = float(value)

    def on_control_rudder(self, ioType, name, valueType, value, myData):
        """Updated pilot rudder pedal input."""
        if value is not None:
            with self._lock:
                self.control_rudder = float(value)

    def on_trim_rudder_feedback(self, ioType, name, valueType, value, myData):
        """Feedback: current trim_rudder value coming back from the aircraft."""
        if value is not None:
            with self._lock:
                self.current_trim = float(value)

    # ──────────────────────────────────────────
    # Thread management
    # ──────────────────────────────────────────

    def _launch_trim_thread(self):
        """Stop any running trim thread, then start a fresh one."""
        self._stop_trim_thread()
        self._stop_event.clear()
        self._trim_thread = threading.Thread(
            target=self._trim_loop,
            daemon=True,
            name="RudderTrimLoop",
        )
        self._trim_thread.start()

    def _stop_trim_thread(self):
        if self._trim_thread and self._trim_thread.is_alive():
            self._stop_event.set()
            self._trim_thread.join(timeout=3.0)
            if self._trim_thread.is_alive():
                print("⚠️  Trim thread did not stop gracefully within 3 s")
            else:
                print("✅  Trim thread stopped")
        self._trim_thread = None

    # ──────────────────────────────────────────
    # Core trim loop
    # ──────────────────────────────────────────

    def _trim_loop(self):
        """
        Continuously adjust trim_rudder to drive slip towards 0.

        The loop keeps running even after stability is achieved, so that if the
        slip drifts again (e.g. pilot moves the rudder) it will re-engage.
        """
        print("▶️  Trim loop started")
        igs.output_set_string("trim_status", "TRIMMING")

        stable_since: float | None = None
        stable_announced = False

        while not self._stop_event.is_set():
            with self._lock:
                slip = self.slip
                control = self.control_rudder
                trim = self.current_trim

            slip_centred = abs(slip) < SLIP_SKID_THRESHOLD
            rudder_released = abs(control) < RUDDER_RELEASE_THRESHOLD

            if slip_centred and rudder_released:
                # ── Stable condition ───────────────────────────────────────
                if stable_since is None:
                    stable_since = time.monotonic()
                    print(f"📐 Slip centred ({slip:.2f}), waiting {STABILITY_REQUIRED:.0f}s for stability…")

                elif not stable_announced and (time.monotonic() - stable_since) >= STABILITY_REQUIRED:
                    print(f"✅ Trim stable for {STABILITY_REQUIRED:.0f}s — monitoring")
                    igs.output_set_string("trim_status", "STABLE")
                    stable_announced = True

            else:
                # ── Trim needed ────────────────────────────────────────────
                if stable_announced:
                    print("⚠️  Stability lost — resuming trim adjustments")
                    igs.output_set_string("trim_status", "TRIMMING")
                    stable_announced = False
                stable_since = None

                if abs(trim) < TRIM_MAX:
                    # Drive trim in the direction that reduces slip
                    # slip > 0 → aircraft yawing right → need left rudder → negative trim
                    # slip < 0 → aircraft yawing left  → need right rudder → positive trim
                    if slip > SLIP_SKID_THRESHOLD:
                        new_trim = trim - TRIM_STEP   # push left
                    elif slip < -SLIP_SKID_THRESHOLD:
                        new_trim = trim + TRIM_STEP   # push right
                    else:
                        new_trim = trim               # within threshold already

                    # Clamp
                    new_trim = max(-TRIM_MAX, min(TRIM_MAX, new_trim))

                    if new_trim != trim:
                        igs.output_set_double("trim_rudder", new_trim)
                        with self._lock:
                            self.current_trim = new_trim

            time.sleep(LOOP_INTERVAL)

        print("🛑  Trim loop exited")
        igs.output_set_string("trim_status", "IDLE")

    def shutdown(self):
        self._stop_trim_thread()


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main():
    print("=" * 50)
    print("Starting Rudder Trim Agent")
    print("=" * 50)

    agent_name = "RudderTrimAgent"
    port = 5670

    if len(sys.argv) >= 2:
        agent_name = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    # ── Ingescape setup ────────────────────────────────────────────────────
    igs.agent_set_name(agent_name)
    igs.log_set_console(True)
    igs.log_set_file(True, None)
    igs.set_command_line(sys.executable + " " + " ".join(sys.argv))

    # Inputs
    igs.input_create("start_trim",           igs.IMPULSION_T, None)
    igs.input_create("stop_trim",            igs.IMPULSION_T, None)
    igs.input_create("slip",                 igs.DOUBLE_T,    None)
    igs.input_create("control_rudder",       igs.DOUBLE_T,    None)
    igs.input_create("trim_rudder_feedback", igs.DOUBLE_T,    None)

    # Outputs
    igs.output_create("trim_rudder", igs.DOUBLE_T,  None)
    igs.output_create("trim_status", igs.STRING_T,  "IDLE")

    agent = RudderTrimAgent()

    # Observe inputs
    igs.observe_input("start_trim",           agent.on_start_trim,           None)
    igs.observe_input("stop_trim",            agent.on_stop_trim,            None)
    igs.observe_input("slip",                 agent.on_slip,                 None)
    igs.observe_input("control_rudder",       agent.on_control_rudder,       None)
    igs.observe_input("trim_rudder_feedback", agent.on_trim_rudder_feedback, None)

    # Mappings — connect to Aircraft and TARS_Agent
    igs.mapping_add("slip",                 "Aircraft",    "slip")
    igs.mapping_add("control_rudder",       "Aircraft",    "controlYaw")
    igs.mapping_add("trim_rudder_feedback", "Aircraft",    "trim_rudder")
    igs.mapping_add("start_trim",           "TARS Agent",  "rudder_trim_start")
    igs.mapping_add("stop_trim",            "TARS Agent",  "rudder_trim_stop")

    # Start
    start_with_device_fallback(igs, port)

    print(f"✓ Rudder Trim Agent '{agent_name}' started on port {port}")
    print("  Inputs : start_trim (impulsion), stop_trim (impulsion), slip, control_rudder, trim_rudder_feedback")
    print("  Outputs: trim_rudder, trim_status")

    # ── Signal handling ────────────────────────────────────────────────────
    def _shutdown(sig, frame):
        print("\n🛑 Rudder Trim Agent interrupted")
        agent.shutdown()
        igs.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        agent.shutdown()
        igs.stop()
        print("Rudder Trim Agent stopped")


if __name__ == "__main__":
    main()
