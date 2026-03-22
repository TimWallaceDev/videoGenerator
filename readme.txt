============================================================
  VIDEO PIPELINE — README
  Automated YouTube video production from a single prompt
============================================================

OVERVIEW
--------
This pipeline takes a single topic string and produces a fully
narrated, illustrated MP4 video ready for YouTube upload.

Pipeline steps:
  1. LLM (Ollama/Qwen) generates a dramatic narration script
  2. Chatterbox TTS (via ComfyUI) generates voice-cloned audio
  3. Whisper transcribes audio and extracts sentence timestamps
  4. Qwen image model (via ComfyUI) generates one image per sentence
  5. ffmpeg assembles everything into a final MP4


REQUIREMENTS
------------
- Python 3.10+
- Ollama (running on localhost:11434)
- ComfyUI (running on localhost:8188)
- ffmpeg (path set in config.py)

Python packages:
  pip install requests websocket-client faster-whisper

ComfyUI custom nodes required:
  - ComfyUI-ChatterboxTTS
  - Qwen Image workflow nodes (built-in as of recent ComfyUI versions)

Models required in Ollama:
  - qwen2.5:14b  (run: ollama pull qwen2.5:14b)

Models required in ComfyUI:
  - qwen_image_fp8_e4m3fn.safetensors          (diffusion_models/)
  - qwen_2.5_vl_7b_fp8_scaled.safetensors      (text_encoders/)
  - qwen_image_vae.safetensors                 (vae/)
  - Qwen-Image-Lightning-4steps-V1.0.safetensors (loras/)
  - Your voice reference file                  (ComfyUI/input/)


PROJECT STRUCTURE
-----------------
~/videoGenerator/
  main.py           — entry point, run this
  config.py         — ALL settings live here, edit this freely
  llm.py            — script + image prompt generation
  tts.py            — Chatterbox audio generation via ComfyUI
  transcribe.py     — Whisper transcription + timestamps
  imagegen.py       — Qwen image generation via ComfyUI
  assemble.py       — ffmpeg video assembly
  workflows/
    chatterbox.json — Chatterbox ComfyUI workflow (API format)
    imagegen.json   — Image gen workflow (not currently used directly)
  output/           — finished MP4s land here
  temp/             — working files, cleared after each run
    images/         — generated images
    audio.wav       — stitched TTS audio
    timestamps.json — Whisper sentence timestamps
    script.txt      — generated script (edit this at checkpoint)
    pipeline_state.json — resume state if pipeline crashes


USAGE
-----
Basic run (with checkpoints):
  python main.py "The rise and fall of BlackBerry"

Fully automated (no checkpoints):
  python main.py "The Christie Pits Riot" --auto

The three checkpoints in manual mode:
  1. After script generation — opens in Notepad for review/editing
  2. After image prompts — review before ~10 min image generation
  3. Before final assembly — last chance to review all assets

RESUME AFTER CRASH:
  If the pipeline crashes, just re-run with the exact same topic.
  Completed steps are skipped automatically via pipeline_state.json.
  Exception: if audio.wav or images are missing, those steps re-run.


CONFIG.PY — KEY SETTINGS
------------------------
OLLAMA_MODEL          Which LLM to use for script generation
FFMPEG / FFPROBE      Full paths to ffmpeg executables
VIDEO_WIDTH/HEIGHT    Output resolution (currently 1280x720)
AUTO_MODE             Set True to always skip checkpoints globally
IMAGE_PROMPT_PREFIX   Grounding tags prepended to every image prompt
SCRIPT_SYSTEM_PROMPT  The main dramatic writing instructions for the LLM
IMAGE_PROMPT_SYSTEM   Instructions for generating image prompts
TARGET_VIDEO_LENGTH   Word count guidance for script length
CHATTERBOX_CHAR_LIMIT Max chars per TTS chunk (keep at 2500 or lower)


KNOWN ISSUES & WORKAROUNDS
---------------------------
1. WEBSOCKET DROPS DURING TTS
   ComfyUI's WebSocket sometimes drops on long Chatterbox generations.
   The pipeline automatically falls back to polling. If ComfyUI crashes
   entirely (CUDA assertion error), the chunk was too long — lower
   CHATTERBOX_CHAR_LIMIT in tts.py (currently 2500).

2. IMAGE COUNT vs TIMESTAMP MISMATCH
   If imagegen times out mid-run, you may end up with fewer images
   than timestamps. The assembler will map what it has and hold the
   last image for remaining sentences. To fix: clear temp/images/,
   delete pipeline_state.json, and re-run to regenerate all images.

3. FIRST IMAGE GENERATION IS SLOW
   The first image generation after starting ComfyUI takes much longer
   (~500s) because it loads the Qwen models into VRAM. Subsequent
   images run at ~20s each. Timeout is set to 600s to accommodate this.

4. SCRIPT TOO SHORT
   If the LLM ignores the word count target, the TARGET_VIDEO_LENGTH
   variable in config.py accepts plain English instructions. Be explicit:
   "write at least 1400 words" works better than "9-12 minutes".

5. AUDIO HAS NO GAPS BETWEEN CHUNKS
   TTS chunks are concatenated directly. Small audible joins between
   chunks are normal. Future improvement: add crossfade in ffmpeg stitch.

6. VIDEO PLAYS IN VLC BUT NOT WINDOWS MEDIA PLAYER
   Normal behaviour with AAC-encoded MP4s from ffmpeg on Windows.
   VLC, YouTube upload, and most modern players handle it fine.


PERFORMANCE (approximate, RTX 4090 mobile)
-------------------------------------------
Script generation:      ~60-90 seconds
TTS audio (10 min):     ~3-5 minutes
Whisper transcription:  ~20-30 seconds
Image generation:       ~20s per image (first image ~500s cold start)
ffmpeg assembly:        ~30 seconds

Total for a 10 min video (~40 images): ~20-25 minutes unattended


TUNING TIPS
-----------
SCRIPT QUALITY:
  - Edit config.py SCRIPT_SYSTEM_PROMPT to adjust tone and style
  - The hook opening rule ("never start with Today we're going to...")
    is the single biggest impact change for YouTube watch time
  - For broader topics beyond GTA, change "Greater Toronto Area" to
    "Canadian history, with a focus on Ontario and the GTA"

IMAGE QUALITY:
  - Edit IMAGE_PROMPT_PREFIX in config.py to change the base style
  - Try "kodachrome photography 1965" or "archival newspaper photograph"
    for more authentic historical feel
  - Increasing steps from 4 to 8 in imagegen.py improves quality
    but doubles generation time

VOICE:
  - Chatterbox parameters are in workflows/chatterbox.json
  - exaggeration (0.5): higher = more emotional, lower = more neutral
  - temperature (0.8): higher = more varied delivery
  - Replace "voice sample 2.mp3" in ComfyUI input folder to change voice


FUTURE IMPROVEMENTS (not yet built)
-------------------------------------
- Batch mode: queue multiple topics from a text file overnight
- Web search / RAG: LLM researches topic before writing
- Intro/outro: ffmpeg overlay with channel branding
- Auto YouTube metadata: generate title, description, tags from script
- Retry logic: auto-retry failed image generations instead of skipping
- Crossfade audio: smooth joins between TTS chunks
- B-roll variety: reuse images less, generate more per sentence group
- Thumbnail generation: separate ComfyUI workflow for YouTube thumbnails


FILE MANAGEMENT
---------------
After a successful run the pipeline offers to clean temp/ automatically.
Output MP4s are saved to output/ with the topic name and timestamp:
  output/the_history_of_scarborough_20260321_161501.mp4

To start completely fresh on a topic:
  1. Delete temp/ contents (or let cleanup run)
  2. Delete pipeline_state.json if it exists
  3. Re-run main.py with your topic


VOICE REFERENCE FILE
--------------------
Your current voice clone reference: "voice sample 2.mp3"
Location: ComfyUI/input/voice sample 2.mp3
Source: ElevenLabs synthetic reference audio
To change voice: drop a new .mp3 into ComfyUI/input/ and update
the filename in workflows/chatterbox.json (widgets_values[0] of node 4)


============================================================
  Built with Claude — Anthropic
  Pipeline version: 1.0
  Last updated: March 2026
============================================================