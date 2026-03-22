# ============================================================
#  BATCH MODE — Overnight Video Queue Processor
#  Reads topics from topics.txt and processes them one by one.
#
#  Usage:
#    python batch.py                  # with checkpoints (not recommended for batch)
#    python batch.py --auto           # fully automated, no stops
#    python batch.py --auto --start 3 # resume from topic #3
#
#  topics.txt format (one topic per line, # for comments):
#    The Avro Arrow
#    The Gerda Munsinger Affair
#    # this line is a comment and will be skipped
#    The Winnipeg General Strike
# ============================================================

import os
import sys
import argparse
import traceback
from datetime import datetime

from main import run_pipeline
from config import BASE_DIR, OUTPUT_DIR


# ------------------------------------------------------------
#  Paths
# ------------------------------------------------------------

TOPICS_FILE = os.path.join(BASE_DIR, "topics.txt")
LOG_FILE    = os.path.join(BASE_DIR, "batch_log.txt")


# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------

def load_topics(filepath: str) -> list[str]:
    """
    Load topics from a text file.
    Skips blank lines and lines starting with #.
    """
    if not os.path.exists(filepath):
        print(f"❌ Topics file not found: {filepath}")
        print(f"   Create it at {filepath} with one topic per line.")
        sys.exit(1)

    topics = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                topics.append(line)

    return topics


def log(message: str):
    """Write a message to both the terminal and batch_log.txt."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def clear_temp():
    """Clear temp files between runs so each video starts fresh."""
    import shutil
    from config import TEMP_DIR, IMAGES_DIR

    temp_files = [
        os.path.join(TEMP_DIR, "audio.wav"),
        os.path.join(TEMP_DIR, "timestamps.json"),
        os.path.join(TEMP_DIR, "script.txt"),
        os.path.join(TEMP_DIR, "pipeline_state.json"),
        os.path.join(TEMP_DIR, "filter_complex.txt"),
        os.path.join(TEMP_DIR, "audio_chunks.txt"),
    ]
    for f in temp_files:
        if os.path.exists(f):
            os.remove(f)

    if os.path.exists(IMAGES_DIR):
        shutil.rmtree(IMAGES_DIR)
    os.makedirs(IMAGES_DIR, exist_ok=True)


# ------------------------------------------------------------
#  Main batch runner
# ------------------------------------------------------------

def run_batch(auto: bool = True, start_index: int = 0):
    """
    Process all topics in topics.txt sequentially.
    Logs results to batch_log.txt.
    """
    topics = load_topics(TOPICS_FILE)

    if not topics:
        print("❌ No topics found in topics.txt")
        sys.exit(1)

    # Apply start index
    if start_index > 0:
        if start_index >= len(topics):
            print(f"❌ --start {start_index} is out of range "
                  f"(only {len(topics)} topics)")
            sys.exit(1)
        topics = topics[start_index:]
        log(f"Resuming from topic #{start_index + 1}")

    total     = len(topics)
    succeeded = []
    failed    = []

    log("=" * 60)
    log(f"BATCH STARTING — {total} topic(s) to process")
    log(f"Auto mode: {auto}")
    log("=" * 60)

    for i, topic in enumerate(topics, 1):
        actual_index = i + start_index
        log(f"")
        log(f"--- Topic {actual_index}/{total + start_index}: {topic} ---")

        # Clear temp from previous run
        clear_temp()

        try:
            output_path = run_pipeline(topic=topic, auto=auto)
            succeeded.append((actual_index, topic, output_path))
            log(f"✅ SUCCESS: {topic}")
            log(f"   Output: {output_path}")

        except KeyboardInterrupt:
            log(f"⚠️  Batch interrupted by user at topic {actual_index}.")
            log(f"   To resume: python batch.py --auto --start {actual_index - 1}")
            _print_summary(succeeded, failed, total + start_index)
            sys.exit(0)

        except Exception as e:
            failed.append((actual_index, topic, str(e)))
            log(f"❌ FAILED: {topic}")
            log(f"   Error: {e}")
            log(f"   Continuing to next topic...")
            # Don't re-raise — keep going through the queue

    # Final summary
    log("")
    log("=" * 60)
    _print_summary(succeeded, failed, total + start_index)
    log("=" * 60)


def _print_summary(
    succeeded: list,
    failed: list,
    total: int
):
    log(f"BATCH COMPLETE")
    log(f"  Total   : {total}")
    log(f"  Success : {len(succeeded)}")
    log(f"  Failed  : {len(failed)}")

    if succeeded:
        log("")
        log("Successful videos:")
        for idx, topic, path in succeeded:
            log(f"  [{idx}] {topic}")
            log(f"       {path}")

    if failed:
        log("")
        log("Failed topics (re-add to topics.txt to retry):")
        for idx, topic, error in failed:
            log(f"  [{idx}] {topic}")
            log(f"       Error: {error}")


# ------------------------------------------------------------
#  Entry point
# ------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process a queue of video topics overnight."
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run fully automated with no checkpoints (recommended for batch)"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        metavar="N",
        help="Skip the first N topics (useful for resuming a failed batch)"
    )

    args = parser.parse_args()

    if not args.auto:
        print("\n⚠️  WARNING: Running batch without --auto means checkpoints")
        print("   will pause execution for every single video.")
        print("   For overnight runs, use: python batch.py --auto\n")
        confirm = input("Continue anyway? (y/n): ").strip().lower()
        if confirm != "y":
            sys.exit(0)

    run_batch(auto=args.auto, start_index=args.start)