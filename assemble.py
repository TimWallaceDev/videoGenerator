# ============================================================
#  ASSEMBLE MODULE — ffmpeg video assembly
#  Takes images + audio + Whisper timestamps and builds
#  the final video with images switching at sentence boundaries.
# ============================================================

import re
import os
import json
import subprocess
import shutil
from datetime import datetime
from config import (
    AUDIO_FILE,
    TIMESTAMPS_FILE,
    IMAGES_DIR,
    OUTPUT_DIR,
    TEMP_DIR,
    VIDEO_FPS,
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    FFMPEG,
    FFPROBE
)

# Full path to ffmpeg bin folder
FFMPEG_BIN = r"C:\Users\RAZER\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
FFMPEG     = os.path.join(FFMPEG_BIN, "ffmpeg.exe")
FFPROBE    = os.path.join(FFMPEG_BIN, "ffprobe.exe")


# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------

def _load_timestamps() -> list[dict]:
    with open(TIMESTAMPS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_audio_duration(audio_path: str) -> float:
    result = subprocess.run([FFMPEG, "-i", audio_path], capture_output=True, text=True)
    for line in result.stderr.splitlines():
        if "Duration" in line:
            time_str = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = time_str.split(":")
            return float(h) * 3600 + float(m) * 60 + float(s)
    raise RuntimeError(f"Could not determine duration of {audio_path}")


def _get_sorted_images(images_dir: str) -> list[str]:
    """Return image paths sorted by filename (img_0001.png, img_0002.png, ...)."""
    files = [
        f for f in os.listdir(images_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ]
    files.sort()
    return [os.path.join(images_dir, f) for f in files]


def _build_filter_complex(
    image_paths: list[str],
    timestamps: list[dict],
    audio_duration: float,
) -> tuple[list[str], str]:
    """
    Build the ffmpeg input args and filter_complex string for
    timestamp-driven image switching.

    Strategy:
    - Each image is a separate input stream (looped)
    - overlay filter switches between images at sentence start times
    - Last image holds until audio ends

    Returns (input_args, filter_complex_string)
    """
    n_images = len(image_paths)
    n_stamps = len(timestamps)

    # Match images to timestamps — if more images than timestamps or vice versa,
    # we map as many as we can and hold the last image for the remainder
    pairs = []
    for i in range(max(n_images, n_stamps)):
        img_idx   = min(i, n_images - 1)
        ts_start  = timestamps[i]["start"] if i < n_stamps else None
        pairs.append((img_idx, ts_start))

    # Build input args — each image is a looped input
    input_args = []
    for path in image_paths:
        input_args += ["-loop", "1", "-i", path]

    # Build filter_complex using the overlay/enable approach
    # Scale each image to target resolution first
    filter_parts = []

    for idx in range(n_images):
        filter_parts.append(
            f"[{idx}:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            f"force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={VIDEO_FPS}[v{idx}]"
        )

    # Build the concat list — each image shown for its duration
    # Calculate duration for each image segment
    segments = []
    for i, (img_idx, ts_start) in enumerate(pairs):
        if i < len(pairs) - 1:
            next_start = pairs[i + 1][1]
            if next_start is not None and ts_start is not None:
                duration = next_start - ts_start
            else:
                duration = audio_duration - (ts_start or 0)
        else:
            duration = audio_duration - (ts_start or 0)

        duration = max(duration, 0.1)  # safety floor
        segments.append((img_idx, duration))

    # Build concat filter
    concat_inputs = ""
    for i, (img_idx, duration) in enumerate(segments):
        filter_parts.append(
            f"[v{img_idx}]trim=duration={duration:.3f},setpts=PTS-STARTPTS[seg{i}]"
        )
        concat_inputs += f"[seg{i}]"

    n_segs = len(segments)
    filter_parts.append(
        f"{concat_inputs}concat=n={n_segs}:v=1:a=0[outv]"
    )

    filter_complex = ";\n".join(filter_parts)
    return input_args, filter_complex


# ------------------------------------------------------------
#  Main function
# ------------------------------------------------------------

def assemble_video(
    image_paths: list[str] = None,
    audio_path: str = None,
    timestamps: list[dict] = None,
    topic: str = "video",
) -> str:
    """
    Assemble the final video from images, audio, and timestamps.
    Returns the path to the output video file.
    """
    # Load from files if not passed directly
    if audio_path is None:
        audio_path = AUDIO_FILE
    if timestamps is None:
        timestamps = _load_timestamps()
    if image_paths is None:
        image_paths = _get_sorted_images(IMAGES_DIR)

    if not image_paths:
        raise FileNotFoundError(f"No images found in {IMAGES_DIR}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    audio_duration = _get_audio_duration(audio_path)
    print(f"📹 Assembling video...")
    print(f"   Images    : {len(image_paths)}")
    print(f"   Timestamps: {len(timestamps)}")
    print(f"   Duration  : {audio_duration:.1f}s")

    # Warn if image/timestamp counts don't match
    if len(image_paths) != len(timestamps):
        print(f"   ⚠️  Image count ({len(image_paths)}) != "
              f"timestamp count ({len(timestamps)}). "
              f"Will map as many as possible.")

    input_args, filter_complex = _build_filter_complex(
        image_paths, timestamps, audio_duration
    )

    # Output filename with timestamp
    safe_topic  = re.sub(r'[^\w\s-]', '', topic).strip().replace(' ', '_')[:50]
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"{safe_topic}_{timestamp}.mp4")

    # Write filter_complex to a temp file to avoid command line length limits
    filter_file = os.path.join(TEMP_DIR, "filter_complex.txt")
    with open(filter_file, "w") as f:
        f.write(filter_complex)

    cmd = (
        [FFMPEG, "-y"]
        + input_args
        + ["-i", audio_path]
        + ["-filter_complex_script", filter_file]
        + [
            "-map", "[outv]",
            "-map", f"{len(image_paths)}:a",  # audio is the last input
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            output_path
        ]
    )

    print(f"   DEBUG cmd: {cmd}")
    print(f"   Running ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stderr[-2000:])  # ADD THIS


    if result.returncode != 0:
        print("\n❌ ffmpeg error:")
        print(result.stderr[-3000:])  # last 3000 chars of stderr
        raise RuntimeError("ffmpeg assembly failed")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ Video saved to {output_path} ({size_mb:.1f} MB)")

    # Clean up filter file
    if os.path.exists(filter_file):
        os.remove(filter_file)

    return output_path


def cleanup_temp():
    """Remove all temp files after a successful run."""
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR)
        os.makedirs(IMAGES_DIR)
    print("🧹 Temp files cleaned up")


# ------------------------------------------------------------
#  Entry point for isolated testing
# ------------------------------------------------------------

if __name__ == "__main__":
    import re
    print("🧪 Testing assemble module...")
    print("   Using existing temp/ files from previous module tests")

    output = assemble_video(topic="scarborough_test")
    print(f"\n✅ Assemble test complete: {output}")