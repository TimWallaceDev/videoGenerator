# ============================================================
#  ASSEMBLE MODULE — ffmpeg video assembly
#  Takes images + audio + Whisper timestamps and builds
#  the final video with images switching at sentence boundaries.
#  Includes Ken Burns zoom effect for cinematic movement.
# ============================================================

import os
import re
import json
import random
import subprocess
import shutil
from datetime import datetime
from config import (
    AUDIO_FILE,
    TIMESTAMPS_FILE,
    IMAGES_DIR,
    OUTPUT_DIR,
    TEMP_DIR,
    VIDEO_CONFIGS,
    FFMPEG,
)

# ------------------------------------------------------------
#  Ken Burns settings
#  ZOOM_START: starting zoom level (1.0 = no zoom)
#  ZOOM_END:   ending zoom level (1.1 = 10% zoom = moderate)
#  Adjust ZOOM_END to taste:
#    Subtle   = 1.05
#    Moderate = 1.10  <-- current setting
#    Dramatic = 1.20
# ------------------------------------------------------------
ZOOM_START = 1.0
ZOOM_END   = 1.1


# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------

def _load_timestamps() -> list[dict]:
    with open(TIMESTAMPS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_audio_duration(audio_path: str) -> float:
    """Use ffmpeg to get the exact duration of the audio file in seconds."""
    result = subprocess.run(
        [FFMPEG, "-i", audio_path],
        capture_output=True, text=True
    )
    for line in result.stderr.splitlines():
        if "Duration" in line:
            time_str = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s  = time_str.split(":")
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


def _kenburns_filter(
    stream_idx: int,
    duration: float,
    width: int,
    height: int,
    fps: int,
    zoom_in: bool,
) -> str:
    """
    Build a Ken Burns zoompan filter for a single image segment.
    The image is scaled to 2x first to give zoom headroom without pixelating.
    """
    n_frames   = max(1, int(duration * fps))
    zoom_range = ZOOM_END - ZOOM_START

    if zoom_in:
        zoom_expr = (
            f"'if(eq(on,1),{ZOOM_START},"
            f"min(zoom+{zoom_range / n_frames:.6f},{ZOOM_END}))'"
        )
    else:
        zoom_expr = (
            f"'if(eq(on,1),{ZOOM_END},"
            f"max(zoom-{zoom_range / n_frames:.6f},{ZOOM_START}))'"
        )

    x_expr = "'iw/2-(iw/zoom/2)'"
    y_expr = "'ih/2-(ih/zoom/2)'"

    return (
        f"[{stream_idx}:v]"
        f"scale={width*2}:{height*2},"
        f"zoompan="
        f"z={zoom_expr}:"
        f"x={x_expr}:"
        f"y={y_expr}:"
        f"d={n_frames}:"
        f"s={width}x{height}:"
        f"fps={fps},"
        f"trim=duration={duration:.3f},"
        f"setpts=PTS-STARTPTS"
        f"[kb{stream_idx}]"
    )


def _build_filter_complex(
    image_paths: list[str],
    timestamps: list[dict],
    audio_duration: float,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
) -> tuple[list[str], str]:
    """
    Build the ffmpeg input args and filter_complex string for
    timestamp-driven image switching with Ken Burns zoom effect.
    Returns (input_args, filter_complex_string)
    """
    n_images = len(image_paths)
    n_stamps = len(timestamps)

    # Match images to timestamps
    pairs = []
    for i in range(max(n_images, n_stamps)):
        img_idx  = min(i, n_images - 1)
        ts_start = timestamps[i]["start"] if i < n_stamps else None
        pairs.append((img_idx, ts_start))

    # Build input args — each image as a looped input
    input_args = []
    for path in image_paths:
        input_args += ["-loop", "1", "-i", path]

    # Calculate duration for each segment
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

        duration = max(duration, 0.5)  # zoompan needs at least a few frames
        segments.append((img_idx, duration))

    # Build Ken Burns filter per segment
    filter_parts   = []
    zoom_directions = {}

    for i, (img_idx, duration) in enumerate(segments):
        if img_idx not in zoom_directions:
            zoom_directions[img_idx] = random.choice([True, False])
        zoom_in = zoom_directions[img_idx]

        kb = _kenburns_filter(img_idx, duration, width, height, fps, zoom_in)
        # Make output tag segment-specific (same image can appear multiple times)
        kb = kb.replace(f"[kb{img_idx}]", f"[kb{i}]")
        filter_parts.append(kb)

    # Concat all segments
    concat_inputs = "".join(f"[kb{i}]" for i in range(len(segments)))
    filter_parts.append(
        f"{concat_inputs}concat=n={len(segments)}:v=1:a=0[outv]"
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
    mode: str = "long",
) -> str:
    """
    Assemble the final video from images, audio, and timestamps.
    Applies Ken Burns zoom effect to each image.
    Returns the path to the output video file.
    """
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
    cfg            = VIDEO_CONFIGS[mode]

    print(f"📹 Assembling video (Ken Burns enabled)...")
    print(f"   Mode      : {mode} ({cfg['width']}x{cfg['height']})")
    print(f"   Images    : {len(image_paths)}")
    print(f"   Timestamps: {len(timestamps)}")
    print(f"   Duration  : {audio_duration:.1f}s")

    if len(image_paths) != len(timestamps):
        print(f"   ⚠️  Image count ({len(image_paths)}) != "
              f"timestamp count ({len(timestamps)}). "
              f"Will map as many as possible.")

    input_args, filter_complex = _build_filter_complex(
        image_paths, timestamps, audio_duration,
        width=cfg["width"], height=cfg["height"], fps=cfg["fps"]
    )

    # Output filename
    safe_topic  = re.sub(r'[^\w\s-]', '', topic).strip().replace(' ', '_')[:50]
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"{safe_topic}_{timestamp}.mp4")

    # Write filter_complex to temp file to avoid command line length limits
    filter_file = os.path.join(TEMP_DIR, "filter_complex.txt")
    with open(filter_file, "w", encoding="utf-8") as f:
        f.write(filter_complex)

    print(f"   Running ffmpeg (zoom processing may take a few extra minutes)...")

    cmd = (
        [FFMPEG, "-y"]
        + input_args
        + ["-i", audio_path]
        + ["-filter_complex_script", filter_file]
        + [
            "-map", "[outv]",
            "-map", f"{len(image_paths)}:a",
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

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("\n❌ ffmpeg error:")
        print(result.stderr[-3000:])
        raise RuntimeError("ffmpeg assembly failed")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ Video saved to {output_path} ({size_mb:.1f} MB)")

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
    print("🧪 Testing assemble module...")
    output = assemble_video(topic="scarborough_test")
    print(f"\n✅ Assemble test complete: {output}")