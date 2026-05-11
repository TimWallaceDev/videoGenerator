# ============================================================
#  ASSEMBLE MODULE — ffmpeg video assembly
#  Takes images + audio + Whisper timestamps and builds
#  the final video with images switching at sentence boundaries.
#  Includes Ken Burns zoom effect and duo captions for Shorts.
#  Supports optional background music with fade in/out.
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
    WORDS_FILE,
    IMAGES_DIR,
    OUTPUT_DIR,
    TEMP_DIR,
    VIDEO_CONFIGS,
    FFMPEG,
    CAPTION_FONT,
    CAPTION_FONT_SIZE,
    CAPTION_COLOR,
    CAPTION_OUTLINE,
    CAPTION_OUTLINE_PX,
    CAPTION_Y_POS,
    CAPTION_WORDS,
    CAPTION_POSITION,
    CAPTION_SIZE_MAP,
    MUSIC_VOLUME,
    MUSIC_FADE_DURATION,
    get_music_file,
)

ZOOM_START = 1.0
ZOOM_END   = 1.1

# Confirmed working font path escaping for this ffmpeg build on Windows.
# C:\Windows\Fonts\arialbd.ttf  →  C\\:/Windows/Fonts/arialbd.ttf
FONT_PATH_ESCAPED = CAPTION_FONT.replace("\\", "/").replace(":/", "\\\\:/")


# ------------------------------------------------------------
#  Caption helpers
# ------------------------------------------------------------

def _sanitize_caption(text: str) -> str:
    """
    Clean text for ffmpeg drawtext filter.
    Replace unicode punctuation with ASCII, then escape
    the two characters that break ffmpeg filter syntax.
    """
    replacements = {
        "\u2018": "'",  "\u2019": "'",
        "\u201c": '"',  "\u201d": '"',
        "\u2013": "-",  "\u2014": "-",
        "\u2026": "...",
        "\u00e9": "e",  "\u00e8": "e",
        "\u00e0": "a",  "\u00e2": "a",
        "\u00f6": "o",  "\u00fc": "u",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # Strip anything still outside printable ASCII
    text = "".join(c for c in text if 32 <= ord(c) < 127)

    # Escape characters that break ffmpeg filter key=value syntax
    text = text.replace("'", "")    # drop apostrophes (safest for filter strings)
    text = text.replace(":", "\\:") # escape colons

    return text.strip()


# Caption position presets — fraction of video height
CAPTION_Y_PRESETS = {
    "top":    0.10,
    "middle": 0.45,
    "bottom": 0.75,
}


def _build_duo_captions(
    words: list[dict],
    audio_duration: float,
    height: int,
    words_per_caption: int = None,
    font_size: int = None,
    position: str = None,
) -> list[str]:
    """
    Build ffmpeg drawtext filter fragments for caption overlay.

    words_per_caption : how many words to show at a time (1, 2, or 3)
    font_size         : pixel size override (uses config default if None)
    position          : "top" | "middle" | "bottom" (uses config default if None)
    """
    if not words:
        return []

    n      = max(1, min(3, words_per_caption or CAPTION_WORDS))
    fsize  = font_size or CAPTION_FONT_SIZE
    pos    = position or CAPTION_POSITION
    y_frac = CAPTION_Y_PRESETS.get(pos, CAPTION_Y_PRESETS["bottom"])
    y_pos  = int(height * y_frac)

    filters = []

    for i in range(0, len(words), n):
        chunk = words[i:i + n]
        text  = " ".join(w["word"].strip() for w in chunk)
        start = chunk[0]["start"]

        if i + n < len(words):
            end = words[i + n]["start"]
        else:
            end = chunk[-1]["end"]

        end = min(end, audio_duration)
        if end <= start:
            continue

        clean = _sanitize_caption(text)
        if not clean:
            continue

        f = (
            f"drawtext="
            f"fontfile={FONT_PATH_ESCAPED}:"
            f"text='{clean}':"
            f"fontcolor={CAPTION_COLOR}:"
            f"fontsize={fsize}:"
            f"borderw={CAPTION_OUTLINE_PX}:"
            f"bordercolor={CAPTION_OUTLINE}:"
            f"x=(w-text_w)/2:"
            f"y={y_pos}:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
        filters.append(f)

    return filters


def _load_words() -> list[dict]:
    if not os.path.exists(WORDS_FILE):
        return []
    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------
#  Ken Burns helpers
# ------------------------------------------------------------

def _load_timestamps() -> list[dict]:
    with open(TIMESTAMPS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_audio_duration(audio_path: str) -> float:
    result = subprocess.run([FFMPEG, "-i", audio_path], capture_output=True, text=True)
    for line in result.stderr.splitlines():
        if "Duration" in line:
            time_str = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s  = time_str.split(":")
            return float(h) * 3600 + float(m) * 60 + float(s)
    raise RuntimeError(f"Could not determine duration of {audio_path}")


def _get_sorted_images(images_dir: str) -> list[str]:
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

    return (
        f"[{stream_idx}:v]"
        f"scale={width*2}:{height*2},"
        f"zoompan="
        f"z={zoom_expr}:"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
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
    final_label: str = "outv",
) -> tuple[list[str], str]:
    """
    Build ffmpeg input args and filter_complex string.
    final_label: the output pad name on the concat filter.
                 Pass "precaption" when a drawtext chain follows.
    """
    n_images = len(image_paths)
    n_stamps = len(timestamps)

    pairs = []
    for i in range(max(n_images, n_stamps)):
        img_idx  = min(i, n_images - 1)
        ts_start = timestamps[i]["start"] if i < n_stamps else None
        pairs.append((img_idx, ts_start))

    input_args = []
    for path in image_paths:
        input_args += ["-loop", "1", "-i", path]

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

        duration = max(duration, 0.5)
        segments.append((img_idx, duration))

    filter_parts    = []
    zoom_directions = {}

    for i, (img_idx, duration) in enumerate(segments):
        if img_idx not in zoom_directions:
            zoom_directions[img_idx] = random.choice([True, False])
        zoom_in = zoom_directions[img_idx]

        kb = _kenburns_filter(img_idx, duration, width, height, fps, zoom_in)
        kb = kb.replace(f"[kb{img_idx}]", f"[kb{i}]")
        filter_parts.append(kb)

    concat_inputs = "".join(f"[kb{i}]" for i in range(len(segments)))
    filter_parts.append(
        f"{concat_inputs}concat=n={len(segments)}:v=1:a=0[{final_label}]"
    )

    return input_args, ";\n".join(filter_parts)


# ------------------------------------------------------------
#  Music mixing
# ------------------------------------------------------------

def _mix_music(
    video_path: str,
    music_path: str,
    audio_duration: float,
    output_path: str,
) -> str:
    """
    Mix background music into an already-assembled video.

    Takes the finished MP4, adds a music track as a second audio input,
    loops it to cover the full duration, fades in/out, reduces volume,
    and mixes with the narration. Outputs a new MP4.

    This runs as a second ffmpeg pass after main assembly, keeping the
    video filter graph completely clean.

    Returns output_path.
    """
    volume    = MUSIC_VOLUME
    fade_dur  = MUSIC_FADE_DURATION
    fade_out_start = max(0.0, audio_duration - fade_dur)

    # Music filter chain:
    # aloop → atrim to exact duration → fade in → fade out → volume reduce
    music_filter = (
        f"[1:a]"
        f"aloop=loop=-1:size=2147483647,"
        f"atrim=duration={audio_duration:.3f},"
        f"afade=t=in:st=0:d={fade_dur:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_dur:.3f},"
        f"volume={volume}"
        f"[music];"
        # Mix narration + music. duration=first keeps narration length.
        # normalize=0 prevents amix from halving both streams' volumes.
        f"[0:a][music]amix=inputs=2:duration=first:normalize=0[aout]"
    )

    cmd = [
        FFMPEG, "-y",
        "-i", video_path,       # input 0: assembled video (video + narration)
        "-i", music_path,       # input 1: music track
        "-filter_complex", music_filter,
        "-map", "0:v",          # video stream from input 0
        "-map", "[aout]",       # mixed audio
        "-c:v", "copy",         # copy video stream — no re-encode needed
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("\n❌ ffmpeg music mix error:")
        print(result.stderr[-2000:])
        raise RuntimeError("ffmpeg music mixing failed")

    return output_path


# ------------------------------------------------------------
#  Main function
# ------------------------------------------------------------

def assemble_video(
    image_paths: list[str] = None,
    audio_path: str = None,
    timestamps: list[dict] = None,
    topic: str = "video",
    mode: str = "long",
    captions: bool = True,
    caption_words: int = None,
    caption_size: str = None,
    caption_position: str = None,
    music_id: str = "none",
) -> str:
    """
    Assemble the final video from images, audio, and timestamps.
    captions         : burn in captions for Shorts
    caption_words    : words per caption chunk (1-3)
    caption_size     : "small" | "medium" | "large"
    caption_position : "top" | "middle" | "bottom"
    music_id         : track ID from config.get_music_tracks(), or "none"
    """
    if audio_path  is None: audio_path  = AUDIO_FILE
    if timestamps  is None: timestamps  = _load_timestamps()
    if image_paths is None: image_paths = _get_sorted_images(IMAGES_DIR)

    if not image_paths:
        raise FileNotFoundError(f"No images found in {IMAGES_DIR}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    audio_duration = _get_audio_duration(audio_path)
    cfg            = VIDEO_CONFIGS[mode]

    # Resolve music path upfront so we can report it early
    music_path = get_music_file(music_id)

    print(f"📹 Assembling video...")
    print(f"   Mode      : {mode} ({cfg['width']}x{cfg['height']})")
    print(f"   Images    : {len(image_paths)}")
    print(f"   Timestamps: {len(timestamps)}")
    print(f"   Duration  : {audio_duration:.1f}s")
    print(f"   Music     : {os.path.basename(music_path) if music_path else 'none'}")

    if len(image_paths) != len(timestamps):
        print(f"   ⚠️  Image/timestamp count mismatch — will map as many as possible.")

    # ----------------------------------------------------------
    #  Decide upfront whether captions are being added.
    # ----------------------------------------------------------
    caption_filters = []
    if mode == "short" and captions:
        words = _load_words()
        if words:
            font_size = CAPTION_SIZE_MAP.get(caption_size or "medium", CAPTION_FONT_SIZE)
            caption_filters = _build_duo_captions(
                words, audio_duration, cfg["height"],
                words_per_caption=caption_words,
                font_size=font_size,
                position=caption_position,
            )

    use_captions = bool(caption_filters)
    final_label  = "precaption" if use_captions else "outv"

    input_args, filter_complex = _build_filter_complex(
        image_paths, timestamps, audio_duration,
        width=cfg["width"], height=cfg["height"], fps=cfg["fps"],
        final_label=final_label,
    )

    if use_captions:
        caption_chain  = "[precaption]" + ",".join(caption_filters) + "[outv]"
        filter_complex = filter_complex + ";\n" + caption_chain
        sz = caption_size or "medium"
        print(f"   Captions  : {len(caption_filters)} chunks ({caption_words or CAPTION_WORDS}w, {sz}, {caption_position or CAPTION_POSITION})")
    elif mode == "short":
        print(f"   Captions  : skipped (words.json not found or empty)")

    # ----------------------------------------------------------
    #  Output paths
    #  If music is requested we write to a temp file first,
    #  then the music pass writes the final output.
    # ----------------------------------------------------------
    safe_topic  = re.sub(r'[^\w\s-]', '', topic).strip().replace(' ', '_')[:50]
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_path  = os.path.join(OUTPUT_DIR, f"{safe_topic}_{timestamp}.mp4")

    if music_path:
        # Write video+narration to a temp file; music pass produces final
        assembly_path = os.path.join(TEMP_DIR, f"_premix_{timestamp}.mp4")
    else:
        assembly_path = final_path

    # Write filter_complex to a temp file to avoid command-line length limits
    filter_file = os.path.join(TEMP_DIR, "filter_complex.txt")
    with open(filter_file, "w", encoding="utf-8") as f:
        f.write(filter_complex)

    print(f"   Running ffmpeg (video assembly)...")

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
            assembly_path,
        ]
    )

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("\n❌ ffmpeg error:")
        print(result.stderr[-3000:])
        raise RuntimeError("ffmpeg assembly failed")

    if os.path.exists(filter_file):
        os.remove(filter_file)

    # ----------------------------------------------------------
    #  Music mixing pass (if requested)
    # ----------------------------------------------------------
    if music_path:
        print(f"   Running ffmpeg (music mix: {os.path.basename(music_path)} @ {MUSIC_VOLUME} vol)...")
        try:
            _mix_music(assembly_path, music_path, audio_duration, final_path)
        finally:
            # Always clean up the premix temp file
            if os.path.exists(assembly_path):
                os.remove(assembly_path)
        print(f"   ✅ Music mixed in")
    
    size_mb = os.path.getsize(final_path) / (1024 * 1024)
    print(f"✅ Video saved to {final_path} ({size_mb:.1f} MB)")

    return final_path


def cleanup_temp():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR)
        os.makedirs(IMAGES_DIR)
    print("🧹 Temp files cleaned up")


# ------------------------------------------------------------
#  Entry point for isolated testing
# ------------------------------------------------------------

if __name__ == "__main__":
    print("🧪 Testing assemble module (Shorts + captions)...")
    output = assemble_video(topic="caption_test", mode="short")
    print(f"\n✅ Done: {output}")