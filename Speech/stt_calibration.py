"""
STT Calibration Script
======================
Say each target word N times. The script records what Vosk actually hears
and saves those detections as the new keywords in speech_commands.py.

Usage:
    python Speech/stt_calibration.py
"""

import sys
import os
import json
import time
import threading
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vosk import Model, KaldiRecognizer
import sounddevice as sd

SAMPLE_RATE = 16000
REPS = 10          # How many times each word is recorded
SILENCE_TIMEOUT = 3.0  # Seconds of silence before auto-stopping a recording
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "model", "vosk-model-en-us-0.22")

# Words to calibrate: (action_name, target_word_to_say)
CALIBRATION_TARGETS = [
    ("acknowledge", "check"),
    ("approve",     "approve"),
    ("deny",        "cancel"),
]

# ── Colours for readability ──────────────────────────────────────────────────
def green(s):  return f"\033[92m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def red(s):    return f"\033[91m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"
def cyan(s):   return f"\033[96m{s}\033[0m"

# ── Single-utterance recorder ────────────────────────────────────────────────
def record_one(model: Model, prompt: str) -> str:
    """
    Open mic, show prompt, wait for speech then silence, return recognised text.
    Press Enter early to skip a rep.
    """
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)
    result_text = ""
    got_speech = False
    last_speech_time = [time.time()]
    done_event = threading.Event()

    def audio_callback(indata, frames, time_info, status):
        nonlocal got_speech, result_text
        if done_event.is_set():
            return
        data = bytes(indata)
        if recognizer.AcceptWaveform(data):
            res = json.loads(recognizer.Result())
            text = res.get("text", "").strip()
            if text:
                got_speech = True
                last_speech_time[0] = time.time()
                result_text = text
        else:
            partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
            if partial:
                got_speech = True
                last_speech_time[0] = time.time()

    # Allow Enter key to skip
    skip = [False]
    def wait_for_enter():
        try:
            input()
        except EOFError:
            pass
        skip[0] = True
        done_event.set()
    enter_thread = threading.Thread(target=wait_for_enter, daemon=True)
    enter_thread.start()

    print(f"  {prompt}  {yellow('(press Enter to skip)')}", end="", flush=True)

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000,
                           dtype="int16", channels=1, callback=audio_callback):
        while not done_event.is_set():
            time.sleep(0.05)
            # Auto-stop after silence following speech
            if got_speech and (time.time() - last_speech_time[0]) > SILENCE_TIMEOUT:
                done_event.set()
            # Safety timeout if no speech at all after 8 s
            if not got_speech and (time.time() - last_speech_time[0]) > 8.0:
                done_event.set()

    # Flush final result
    final = json.loads(recognizer.FinalResult()).get("text", "").strip()
    if final:
        result_text = final

    if skip[0] and not result_text:
        print(f"  {yellow('skipped')}")
        return ""

    return result_text.strip()


# ── Update speech_commands.py in-place ──────────────────────────────────────
SPEECH_COMMANDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Core", "speech_commands.py"
)

def update_keywords(action: str, new_keywords: list[str]) -> bool:
    """
    Find the Command block for `action` in speech_commands.py and replace
    its keywords list with new_keywords, preserving all other fields.
    """
    with open(SPEECH_COMMANDS_PATH, "r", encoding="utf-8") as fh:
        source = fh.read()

    # Find the block:   action="<action>",\n    keywords=[...]
    pattern = (
        r'(action\s*=\s*"' + re.escape(action) + r'",\s*\n'
        r'\s*keywords\s*=\s*\[)[^\]]*(\])'
    )

    formatted = json.dumps(new_keywords, ensure_ascii=False)
    # Wrap long list nicely
    if len(formatted) > 80:
        items = ",\n                  ".join(f'"{k}"' for k in new_keywords)
        formatted = f"[{items}]"

    new_source, count = re.subn(pattern, r'\g<1>' + formatted.lstrip('['), source,
                                 flags=re.DOTALL)
    # re.subn gives back the closing ] already in group 2 replacement
    # Redo cleanly:
    def replacer(m):
        return m.group(1) + formatted[1:]   # formatted includes the closing ]

    new_source = re.sub(pattern, replacer, source, flags=re.DOTALL)
    if new_source == source:
        return False  # Nothing changed / pattern not found

    with open(SPEECH_COMMANDS_PATH, "w", encoding="utf-8") as fh:
        fh.write(new_source)
    return True


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(bold("\n" + "=" * 60))
    print(bold("  STT CALIBRATION"))
    print(bold("=" * 60))
    print(f"\nUsing model: {MODEL_PATH}")

    if not os.path.exists(MODEL_PATH):
        print(red(f"❌ Model not found at {MODEL_PATH}"))
        sys.exit(1)

    print("\n📦 Loading Vosk model (may take 30-60 s on first run)...")
    model = Model(MODEL_PATH)
    print(green("✅ Model loaded\n"))

    calibration_results: dict[str, list[str]] = {}   # action → [detected words]

    for action, target_word in CALIBRATION_TARGETS:
        print(bold(f"\n{'─'*60}"))
        print(bold(f"  Command: {cyan(action.upper())}  →  say: {green(repr(target_word))}"))
        print(f"  You will be prompted {REPS} times. Say {green(repr(target_word))} clearly each time.")
        print(f"  Recording stops automatically after {SILENCE_TIMEOUT}s of silence.")
        print(bold(f"{'─'*60}"))
        input(f"\n  Press Enter when ready...")

        detections: list[str] = []

        for i in range(1, REPS + 1):
            prompt = f"[{i}/{REPS}] 🎤 Say {green(repr(target_word))}..."
            detected = record_one(model, prompt)

            if detected:
                # Strip punctuation
                words = [w.strip(".,!?") for w in detected.lower().split() if w.strip(".,!?")]
                detections.extend(words)
                print(f"\r  [{i}/{REPS}] Heard: {green(repr(detected))}")
            else:
                print(f"\r  [{i}/{REPS}] {yellow('(nothing detected)')}")

        calibration_results[action] = detections
        unique = sorted(set(detections))
        print(f"\n  Detections for {cyan(action)}: {unique}")

    # ── Summary & confirmation ───────────────────────────────────────────────
    print(bold(f"\n{'='*60}"))
    print(bold("  CALIBRATION SUMMARY"))
    print(bold(f"{'='*60}\n"))

    proposed: dict[str, list[str]] = {}
    for action, detections in calibration_results.items():
        if not detections:
            print(yellow(f"  {action}: no detections — skipping"))
            continue

        # Unique detected words, keep all (they're what Vosk will output)
        words = sorted(set(detections))
        proposed[action] = words
        print(f"  {cyan(action):20s}  detected words: {green(str(words))}")

    print()
    answer = input("Apply these as new keywords to speech_commands.py? [y/N] ").strip().lower()

    if answer != "y":
        print(yellow("Aborted — no changes made."))
        sys.exit(0)

    updated = []
    skipped = []
    for action, words in proposed.items():
        if update_keywords(action, words):
            updated.append(action)
            print(green(f"  ✅ Updated keywords for '{action}'"))
        else:
            skipped.append(action)
            print(red(f"  ❌ Could not find/update '{action}' in speech_commands.py"))

    if updated:
        print(green(f"\n✅ Done. Updated: {updated}"))
        print(f"   Edit {SPEECH_COMMANDS_PATH}")
        print(f"   to review or tweak further.")
    if skipped:
        print(yellow(f"⚠️  Skipped (pattern not matched): {skipped}"))


if __name__ == "__main__":
    main()
