# ============================================================
#  BATCH MODE — Overnight Video Queue Processor
#
#  Usage:
#    python batch.py --auto
#    python batch.py --auto --start 3
#    python batch.py --auto --style funny
#
#  topics.txt format (one topic per line, # for comments):
#    The Avro Arrow
#    The Stanford Prison Experiment
#    # this line is skipped
#    Why cats knock things off tables | funny
#    A short history of salt | serious | short
#
#  Inline overrides (pipe-separated, optional):
#    topic | style | mode
#    style and mode default to CLI args if not specified per-line
# ============================================================

import os
import sys
import argparse
import traceback
from datetime import datetime

from main   import run_pipeline
from config import BASE_DIR, OUTPUT_DIR, COMFYUI_RESTART_EVERY
import comfyui

TOPICS_FILE = os.path.join(BASE_DIR, "topics.txt")
LOG_FILE    = os.path.join(BASE_DIR, "batch_log.txt")


# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------

def load_topics(filepath: str) -> list[dict]:
    """
    Load topics from topics.txt.
    Each line can optionally include style and mode overrides:
      topic
      topic | funny
      topic | funny | short
    Returns list of dicts: {topic, style, mode} with None meaning "use CLI default".
    """
    if not os.path.exists(filepath):
        print(f"❌ Topics file not found: {filepath}")
        sys.exit(1)

    items = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts  = [p.strip() for p in line.split("|")]
            topic  = parts[0]
            style  = parts[1] if len(parts) > 1 and parts[1] in ("serious", "funny") else None
            mode   = parts[2] if len(parts) > 2 and parts[2] in ("long", "short")    else None

            if topic:
                items.append({"topic": topic, "style": style, "mode": mode})

    return items


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def clear_temp():
    """Clear all temp files between runs so each video starts completely fresh."""
    import shutil
    from config import TEMP_DIR, IMAGES_DIR

    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR,   exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)


# ------------------------------------------------------------
#  Main batch runner
# ------------------------------------------------------------

def run_batch(
    auto: bool        = True,
    start_index: int  = 0,
    default_style: str = "serious",
    default_mode: str  = "long",
):
    topics = load_topics(TOPICS_FILE)

    if not topics:
        print("❌ No topics found in topics.txt")
        sys.exit(1)

    if start_index > 0:
        if start_index >= len(topics):
            print(f"❌ --start {start_index} out of range ({len(topics)} topics)")
            sys.exit(1)
        topics = topics[start_index:]
        log(f"Resuming from topic #{start_index + 1}")

    total     = len(topics)
    succeeded = []
    failed    = []

    log("=" * 60)
    log(f"BATCH STARTING — {total} topic(s) | style={default_style} | mode={default_mode}")
    log(f"ComfyUI restart every {COMFYUI_RESTART_EVERY} videos")
    log("=" * 60)

    # Start ComfyUI fresh at the beginning of every batch run
    if not comfyui.start():
        log("❌ ComfyUI failed to start. Aborting batch.")
        sys.exit(1)

    for i, item in enumerate(topics, 1):
        actual_index = i + start_index
        style = item["style"] or default_style
        mode  = item["mode"]  or default_mode

        log("")
        log(f"--- Topic {actual_index}/{total + start_index}: {item['topic']} [{style}/{mode}] ---")

        # Clear temp from previous run
        clear_temp()

        # Restart ComfyUI every N videos to flush accumulated VRAM
        if COMFYUI_RESTART_EVERY > 0 and i > 1 and (i - 1) % COMFYUI_RESTART_EVERY == 0:
            log(f"🔄 Scheduled ComfyUI restart after {i - 1} videos")
            if not comfyui.restart():
                log("❌ ComfyUI failed to restart. Aborting batch.")
                log(f"   To resume: python batch.py --auto --start {actual_index - 1}")
                _print_summary(succeeded, failed, total + start_index)
                sys.exit(1)

        try:
            output_path = run_pipeline(
                topic=item["topic"],
                auto=auto,
                mode=mode,
                style=style,
            )
            succeeded.append((actual_index, item["topic"], output_path))
            log(f"✅ SUCCESS: {item['topic']}")
            log(f"   Output: {output_path}")

        except KeyboardInterrupt:
            log(f"⚠️  Batch interrupted at topic {actual_index}.")
            log(f"   To resume: python batch.py --auto --start {actual_index - 1}")
            _print_summary(succeeded, failed, total + start_index)
            sys.exit(0)

        except Exception as e:
            failed.append((actual_index, item["topic"], str(e)))
            log(f"❌ FAILED: {item['topic']}")
            log(f"   Error: {e}")
            log(f"   Continuing to next topic...")

    log("")
    log("=" * 60)
    _print_summary(succeeded, failed, total + start_index)
    log("=" * 60)

    # Leave ComfyUI running after batch completes
    # (don't stop it — user may want to use it manually after)


def _print_summary(succeeded, failed, total):
    log(f"BATCH COMPLETE — {total} total | {len(succeeded)} succeeded | {len(failed)} failed")

    if succeeded:
        log("Successful:")
        for idx, topic, path in succeeded:
            log(f"  [{idx}] {topic} → {path}")

    if failed:
        log("Failed (re-add to topics.txt to retry):")
        for idx, topic, error in failed:
            log(f"  [{idx}] {topic}")
            log(f"       {error}")


# ------------------------------------------------------------
#  Entry point
# ------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto",  action="store_true")
    parser.add_argument("--start", type=int, default=0, metavar="N")
    parser.add_argument("--style", choices=["serious", "funny"], default="serious")
    parser.add_argument("--mode",  choices=["long", "short"],    default="long")

    args = parser.parse_args()

    if not args.auto:
        print("\n⚠️  Running batch without --auto means checkpoints at every video.")
        print("   For overnight runs use: python batch.py --auto\n")
        if input("Continue anyway? (y/n): ").strip().lower() != "y":
            sys.exit(0)

    run_batch(
        auto=args.auto,
        start_index=args.start,
        default_style=args.style,
        default_mode=args.mode,
    )