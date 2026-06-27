# ============================================================
#  VIDEO PIPELINE — MAIN ORCHESTRATOR
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
    TEMP_DIR, OUTPUT_DIR, IMAGES_DIR,
    TIMESTAMPS_FILE, AUDIO_FILE, VIDEO_CONFIGS,
    VIDEO_STYLE, DEFAULT_VOICE_ID, CAPTIONS_DEFAULT,
    CAPTION_WORDS, CAPTION_POSITION,
    DEFAULT_IMAGE_MODEL_ID, DEFAULT_MUSIC_ID,
)


def checkpoint(label: str, auto: bool):
    if auto:
        return
    print(f"\n{'='*60}\n  CHECKPOINT: {label}\n{'='*60}")
    input("  Press Enter to continue, or Ctrl+C to abort...\n")


STATE_FILE = os.path.join(TEMP_DIR, "pipeline_state.json")

def save_state(state: dict):
    os.makedirs(TEMP_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def clear_state():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


# ------------------------------------------------------------
#  Main pipeline
# ------------------------------------------------------------

def run_pipeline(
    topic:            str,
    auto:             bool = False,
    mode:             str  = "long",
    style:            str  = "serious",
    voice_id:         str  = None,
    captions:         bool = None,
    caption_words:    int  = None,
    caption_size:     str  = None,
    caption_position: str  = None,
    style_notes:      str  = "",
    script:           str  = None,
    image_model_id:   str  = None,
    music_id:         str  = None,
    skip_research:    bool = False,
):
    """
    Full pipeline from topic string to finished .mp4.

    voice_id         : ID from config.VOICES. Defaults to DEFAULT_VOICE_ID.
    captions         : Whether to burn in captions (Shorts only).
    caption_words    : Words per caption chunk (1-3).
    caption_size     : "small" | "medium" | "large"
    caption_position : "top" | "middle" | "bottom"
    style_notes      : Optional free-text modifier appended to the script prompt.
    script           : If provided, skip research + LLM script generation entirely
                       and use this text as the script verbatim.
    image_model_id   : ID from config.IMAGE_MODELS. Defaults to DEFAULT_IMAGE_MODEL_ID.
    music_id         : ID from config.get_music_tracks(). Defaults to DEFAULT_MUSIC_ID.
    """
    if voice_id is None:
        voice_id = DEFAULT_VOICE_ID
    if captions is None:
        captions = CAPTIONS_DEFAULT
    if caption_words is None:
        caption_words = CAPTION_WORDS
    if caption_position is None:
        caption_position = CAPTION_POSITION
    if image_model_id is None:
        image_model_id = DEFAULT_IMAGE_MODEL_ID
    if music_id is None:
        music_id = DEFAULT_MUSIC_ID

    cfg        = VIDEO_CONFIGS[mode]
    start_time = datetime.now()

    clear_state()

    print(f"\n{'='*60}")
    print(f"  🎬 VIDEO PIPELINE STARTING")
    print(f"  Topic    : {topic}")
    print(f"  Mode     : {'AUTO' if auto else 'MANUAL'} | {mode.upper()} ({cfg['width']}x{cfg['height']})")
    print(f"  Style    : {style.upper()}")
    print(f"  Voice    : {voice_id}")
    print(f"  ImgModel : {image_model_id}")
    print(f"  Music    : {music_id}")
    print(f"  Captions : {captions}" + (f" | {caption_words}w | {caption_size or 'medium'} | {caption_position}" if captions and mode == "short" else ""))
    if script:
        print(f"  Script   : provided ({len(script.split())} words)")
    if style_notes:
        print(f"  Notes    : {style_notes}")
    print(f"  Time     : {start_time.strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")

    os.makedirs(TEMP_DIR,   exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    # --------------------------------------------------------
    #  STEP 1 — Research + Script (skipped if script provided)
    # --------------------------------------------------------
    if script:
        pipeline_status.update("Script", 1, "Using provided script", 20)
        print("[ Step 1 / 5 ] — Script (provided, skipping research + generation)")
        script = script.strip()
    elif skip_research:
        pipeline_status.update("Script", 1, "Generating script (no research)...", 10)
        print("[ Step 1 / 5 ] — Script generation (research skipped)")
        script = generate_script(
            topic, auto=auto, research="",
            mode=mode, style=style, style_notes=style_notes,
        )
        save_state({"script": script, "style": style})
    else:
        pipeline_status.update("Research + Script", 1, "Researching topic...", 5)
        print("[ Step 1 / 5 ] — Research + Script generation")
        research = research_topic(topic)
        script   = generate_script(
            topic, auto=auto, research=research,
            mode=mode, style=style, style_notes=style_notes,
        )
        save_state({"script": script, "style": style})

    sentences = split_into_sentences(script)
    print(f"             {len(script.split())} words, {len(sentences)} sentences\n")

    # --------------------------------------------------------
    #  STEP 2 — Image prompts
    # --------------------------------------------------------
    pipeline_status.update("Image Prompts", 2, "Generating prompts...", 25)
    print("[ Step 2 / 5 ] — Image prompt generation")
    if not script:
        checkpoint("Review script before generating image prompts", auto)
    prompts = generate_image_prompts(sentences, auto=auto, style=style)
    print(f"             {len(prompts)} prompts\n")
    checkpoint("Review image prompts before starting image generation", auto)

    # --------------------------------------------------------
    #  STEP 3 — Audio
    # --------------------------------------------------------
    pipeline_status.update("Audio", 3, "Generating voice audio...", 40)
    print("[ Step 3 / 5 ] — Audio generation (Chatterbox)")
    generate_audio(script, voice_id=voice_id)

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
    pipeline_status.update("Image Generation", 5, f"Generating {len(prompts)} images...", 60)
    print(f"[ Step 5 / 5 ] — Image generation ({len(prompts)} images, ~{est_secs//60}m {est_secs%60}s)")
    image_paths = generate_images(prompts, mode=mode, model_id=image_model_id)

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
        captions=captions,
        caption_words=caption_words,
        caption_size=caption_size,
        caption_position=caption_position,
        music_id=music_id,
    )

    # Save script alongside the video with a matching filename
    script_txt_path = os.path.splitext(output_path)[0] + ".txt"
    with open(script_txt_path, "w", encoding="utf-8") as f:
        f.write(script)
    print(f"   📄 Script saved: {os.path.basename(script_txt_path)}")

    elapsed = datetime.now() - start_time
    print(f"\n{'='*60}")
    print(f"  ✅ PIPELINE COMPLETE!")
    print(f"  Output : {output_path}")
    print(f"  Time   : {int(elapsed.total_seconds()//60)}m {int(elapsed.total_seconds()%60)}s")
    print(f"{'='*60}\n")

    if not auto:
        if input("  Clean up temp files? (y/n): ").strip().lower() == "y":
            cleanup_temp()
    else:
        cleanup_temp()

    clear_state()
    return output_path


# ------------------------------------------------------------
#  Entry point
# ------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("topic", type=str)
    parser.add_argument("--auto",        action="store_true")
    parser.add_argument("--mode",        choices=["long", "short"],    default="long")
    parser.add_argument("--style",       choices=["serious", "funny"], default=VIDEO_STYLE)
    parser.add_argument("--voice",       type=str, default=DEFAULT_VOICE_ID,
                        help="Voice ID from config.VOICES")
    parser.add_argument("--image-model", type=str, default=DEFAULT_IMAGE_MODEL_ID,
                        help="Image model ID from config.IMAGE_MODELS")
    parser.add_argument("--script",            type=str, default=None,
                        help="Path to a .txt file containing the script to use verbatim")
    parser.add_argument("--no-captions",      action="store_true",
                        help="Disable captions for Shorts")
    parser.add_argument("--caption-words",    type=int, default=None, choices=[1,2,3],
                        help="Words per caption chunk (default: 2)")
    parser.add_argument("--caption-size",     type=str, default=None,
                        choices=["small","medium","large"])
    parser.add_argument("--caption-position", type=str, default=None,
                        choices=["top","middle","bottom"])
    parser.add_argument("--notes",       type=str, default="",
                        help='Style notes, e.g. "focus on the psychology angle"')
    parser.add_argument("--music",       type=str, default=DEFAULT_MUSIC_ID,
                        help="Music track ID (stem of filename in music/ dir, or 'none')")

    args = parser.parse_args()

    try:
        provided_script = None
        if args.script:
            with open(args.script, "r", encoding="utf-8") as f:
                provided_script = f.read()

        run_pipeline(
            topic=args.topic,
            auto=args.auto,
            mode=args.mode,
            style=args.style,
            voice_id=args.voice,
            captions=not args.no_captions,
            caption_words=args.caption_words,
            caption_size=args.caption_size,
            caption_position=args.caption_position,
            style_notes=args.notes,
            script=provided_script,
            image_model_id=args.image_model,
            music_id=args.music,
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        traceback.print_exc()
        sys.exit(1)
