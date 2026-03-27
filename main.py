# ============================================================
#  VIDEO PIPELINE — MAIN ORCHESTRATOR
#  Usage:
#    python main.py "The Stanford Prison Experiment"
#    python main.py "The Avro Arrow" --auto
#    python main.py "Crazy fact" --auto --mode short --style funny
# ============================================================

import os
import sys
import json
import argparse
import traceback
from datetime import datetime

from llm        import generate_script, generate_image_prompts, split_into_sentences
from tts        import generate_audio
from transcribe import transcribe_audio
from imagegen   import generate_images
from assemble   import assemble_video, cleanup_temp
from research   import research_topic
from status     import pipeline_status

from config import (
    TEMP_DIR,
    OUTPUT_DIR,
    IMAGES_DIR,
    TIMESTAMPS_FILE,
    AUDIO_FILE,
    VIDEO_CONFIGS,
    VIDEO_STYLE,
)


# ------------------------------------------------------------
#  Checkpoint helper
# ------------------------------------------------------------

def checkpoint(label: str, auto: bool):
    if auto:
        return
    print(f"\n{'='*60}")
    print(f"  CHECKPOINT: {label}")
    print(f"{'='*60}")
    input("  Press Enter to continue, or Ctrl+C to abort...\n")


# ------------------------------------------------------------
#  Pipeline state
# ------------------------------------------------------------

STATE_FILE = os.path.join(TEMP_DIR, "pipeline_state.json")

def save_state(state: dict):
    os.makedirs(TEMP_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def clear_state():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


# ------------------------------------------------------------
#  Main pipeline
# ------------------------------------------------------------

def run_pipeline(
    topic: str,
    auto: bool = False,
    mode: str = "long",
    style: str = "serious",
):
    cfg        = VIDEO_CONFIGS[mode]
    start_time = datetime.now()

    # Always clear state at the start of a new run.
    # This prevents the previous video's state from bleeding
    # into the next topic when running via batch or server.
    clear_state()

    print(f"\n{'='*60}")
    print(f"  🎬 VIDEO PIPELINE STARTING")
    print(f"  Topic : {topic}")
    print(f"  Mode  : {'AUTO' if auto else 'MANUAL'} | {mode.upper()}"
          f" ({cfg['width']}x{cfg['height']})")
    print(f"  Style : {style.upper()}")
    print(f"  Time  : {start_time.strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")

    os.makedirs(TEMP_DIR,   exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    state = {}  # always start fresh — resume logic removed (see batch.py for context)

    # --------------------------------------------------------
    #  STEP 1 — Research + Script
    # --------------------------------------------------------
    pipeline_status.update("Research + Script", 1, "Researching topic...", 5)
    print("[ Step 1 / 5 ] — Research + Script generation")
    research = research_topic(topic)
    script   = generate_script(topic, auto=auto, research=research, mode=mode, style=style)
    state["script"] = script
    state["style"]  = style
    save_state(state)

    sentences = split_into_sentences(script)
    print(f"             {len(script.split())} words, {len(sentences)} sentences\n")

    # --------------------------------------------------------
    #  STEP 2 — Image prompts
    # --------------------------------------------------------
    pipeline_status.update("Image Prompts", 2, "Generating prompts...", 25)
    print("[ Step 2 / 5 ] — Image prompt generation")
    checkpoint("Review script before generating image prompts", auto)
    prompts = generate_image_prompts(sentences, auto=auto, style=style)
    state["prompts"] = prompts
    save_state(state)
    print(f"             {len(prompts)} prompts\n")
    checkpoint("Review image prompts before starting image generation", auto)

    # --------------------------------------------------------
    #  STEP 3 — Audio
    # --------------------------------------------------------
    pipeline_status.update("Audio", 3, "Generating voice audio...", 40)
    print("[ Step 3 / 5 ] — Audio generation (Chatterbox)")
    generate_audio(script)

    # --------------------------------------------------------
    #  STEP 4 — Transcribe
    # --------------------------------------------------------
    pipeline_status.update("Transcription", 4, "Running Whisper...", 55)
    print("[ Step 4 / 5 ] — Transcription (Whisper)")
    timestamps = transcribe_audio(AUDIO_FILE, script_sentences=sentences)

    # --------------------------------------------------------
    #  STEP 5 — Images
    # --------------------------------------------------------
    est_secs = len(prompts) * 45
    pipeline_status.update("Image Generation", 5,
                            f"Generating {len(prompts)} images...", 60)
    print(f"[ Step 5 / 5 ] — Image generation "
          f"({len(prompts)} images, ~{est_secs // 60}m {est_secs % 60}s)")
    image_paths = generate_images(prompts, mode=mode)

    # --------------------------------------------------------
    #  FINAL — Assemble
    # --------------------------------------------------------
    pipeline_status.update("Assembly", 5, "Assembling final video...", 90)
    print("\n[ Final ] — Assembling video")
    checkpoint("All assets ready — review before final assembly", auto)

    output_path = assemble_video(
        image_paths=image_paths,
        audio_path=AUDIO_FILE,
        timestamps=timestamps,
        topic=topic,
        mode=mode,
    )

    elapsed = datetime.now() - start_time
    mins    = int(elapsed.total_seconds() // 60)
    secs    = int(elapsed.total_seconds() % 60)

    print(f"\n{'='*60}")
    print(f"  ✅ PIPELINE COMPLETE!")
    print(f"  Output : {output_path}")
    print(f"  Time   : {mins}m {secs}s")
    print(f"{'='*60}\n")

    if not auto:
        if input("  Clean up temp files? (y/n): ").strip().lower() == "y":
            cleanup_temp()
    else:
        cleanup_temp()

    clear_state()
    return output_path


def _get_existing_images() -> list[str]:
    if not os.path.exists(IMAGES_DIR):
        return []
    files = [f for f in os.listdir(IMAGES_DIR)
             if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    files.sort()
    return [os.path.join(IMAGES_DIR, f) for f in files]


# ------------------------------------------------------------
#  Entry point
# ------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("topic", type=str)
    parser.add_argument("--auto",  action="store_true")
    parser.add_argument("--mode",  choices=["long", "short"],    default="long")
    parser.add_argument("--style", choices=["serious", "funny"], default=VIDEO_STYLE)

    args = parser.parse_args()

    try:
        run_pipeline(topic=args.topic, auto=args.auto, mode=args.mode, style=args.style)
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        traceback.print_exc()
        sys.exit(1)