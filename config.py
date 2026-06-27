# ============================================================
#  VIDEO PIPELINE — CENTRAL CONFIG
# ============================================================

import os
import glob

# --- Paths ---
BASE_DIR        = os.path.expanduser("~/videoGenerator")
TEMP_DIR        = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR      = os.path.join(BASE_DIR, "output")
IMAGES_DIR      = os.path.join(TEMP_DIR, "images")
WORKFLOWS_DIR   = os.path.join(BASE_DIR, "workflows")

SCRIPT_FILE     = os.path.join(TEMP_DIR, "script.txt")
AUDIO_FILE      = os.path.join(TEMP_DIR, "audio.wav")
TIMESTAMPS_FILE = os.path.join(TEMP_DIR, "timestamps.json")
WORDS_FILE      = os.path.join(TEMP_DIR, "words.json")

# --- Ollama ---
OLLAMA_MODEL    = "dolphin-llama3:latest"
OLLAMA_BASE_URL = "http://localhost:11434"

# --- ComfyUI ---
COMFYUI_URL     = "http://localhost:8188"
CHATTERBOX_WORKFLOW = os.path.join(WORKFLOWS_DIR, "chatterbox.json")

COMFYUI_PATH          = r"C:\Users\RAZER\comfy\ComfyUI\ComfyUI\main.py"
COMFYUI_RESTART_EVERY = 5

# --- ffmpeg ---
FFMPEG_BIN = r"C:\Users\RAZER\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
FFMPEG     = os.path.join(FFMPEG_BIN, "ffmpeg.exe")
FFPROBE    = os.path.join(FFMPEG_BIN, "ffprobe.exe")

# --- Captions ---
CAPTION_STYLE      = "duo"
CAPTION_FONT       = r"C:\Windows\Fonts\arialbd.ttf"
CAPTION_FONT_SIZE  = 72
CAPTION_COLOR      = "white"
CAPTION_OUTLINE    = "black"
CAPTION_OUTLINE_PX = 4
CAPTION_Y_POS      = 0.75

# Whether captions are enabled by default for Shorts.
# Overridden at runtime by the frontend / CLI.
CAPTIONS_DEFAULT = True

# Caption defaults — all overridable per-video from the UI or CLI
CAPTION_WORDS    = 2        # words shown per caption chunk (1, 2, or 3)
CAPTION_POSITION = "bottom" # "top" | "middle" | "bottom"

# Font size presets — maps size label to pixel value
CAPTION_SIZE_MAP = {
    "small":  52,
    "medium": 72,
    "large":  96,
}

# --- Pipeline behaviour ---
AUTO_MODE = False

# --- Video mode configs ---
VIDEO_CONFIGS = {
    "long": {
        "width":   1280,
        "height":  720,
        "fps":     30,
    },
    "short": {
        "width":   720,
        "height":  1280,
        "fps":     30,
    },
}

VIDEO_MODE   = "long"
VIDEO_WIDTH  = VIDEO_CONFIGS[VIDEO_MODE]["width"]
VIDEO_HEIGHT = VIDEO_CONFIGS[VIDEO_MODE]["height"]
VIDEO_FPS    = VIDEO_CONFIGS[VIDEO_MODE]["fps"]

# --- Default style ---
VIDEO_STYLE = "serious"

# ============================================================
#  VOICES
#  Each entry is a dict with:
#    id    — unique key used in the API and stored in queue
#    label — human-readable name shown in the UI
#    file  — filename inside ComfyUI/input/ (must exist there)
# ============================================================

VOICES = [
    {"id": "en_default",  "label": "EN — Default",     "file": "EN - Sample.mp3"},
    {"id": "en_voice2",   "label": "EN — Voice 2",      "file": "voice sample 2.mp3"},
    {"id": "en_ss",       "label": "EN — SS",           "file": "SS voice sample.mp3"},
    {"id": "es_sample",   "label": "ES — Spanish",      "file": "ES - Sample.mp3"},
    {"id": "pt_sample",   "label": "PT — Portuguese",   "file": "PT - Sample.mp3"},
    {"id": "pt_voice2",   "label": "PT — Portuguese 2", "file": "PT - Voice Sample 2 .mp3"},
]

# The voice used when none is specified
DEFAULT_VOICE_ID = "en_default"

def get_voice_file(voice_id: str) -> str:
    """Return the ComfyUI input filename for a given voice ID."""
    for v in VOICES:
        if v["id"] == voice_id:
            return v["file"]
    for v in VOICES:
        if v["id"] == DEFAULT_VOICE_ID:
            return v["file"]
    return VOICES[0]["file"]


# ============================================================
#  IMAGE MODELS
#  Each entry is a full ComfyUI API-format workflow (in workflows/)
#  plus a small injection map telling imagegen.py where to plug in
#  the prompt, negative prompt, resolution, and seed.
#
#  Map fields:
#    workflow       — filename in WORKFLOWS_DIR
#    prompt_node    — node ID for the positive CLIPTextEncode
#    negative_node  — node ID for negative prompt, or None if the
#                      model has no negative prompt concept
#    latent_node    — node ID with width/height inputs
#    extra_size_nodes — list of additional (node_id, width_key, height_key)
#                      tuples that also need resolution updates
#                      (e.g. Flux's ModelSamplingFlux node)
#    seed_node      — node ID holding the seed
#    seed_key       — field name for the seed ("seed" or "noise_seed")
# ============================================================

IMAGE_MODELS = [
    {
        "id":          "sdxl_fast",
        "label":       "SDXL — Fast",
        "workflow":    "sdxl_fast.json",
        "prompt_node":   "6",
        "negative_node": "7",
        "latent_node":   "5",
        "extra_size_nodes": [],
        "seed_node": "3",
        "seed_key":  "seed",
    },
    {
        "id":          "z_image",
        "label":       "Z-Image",
        "workflow":    "z_image.json",
        "prompt_node":   "76:67",
        "negative_node": "76:71",
        "latent_node":   "76:68",
        "extra_size_nodes": [],
        "seed_node": "76:69",
        "seed_key":  "seed",
    },
    {
        "id":          "z_image_turbo",
        "label":       "Z-Image Turbo",
        "workflow":    "z_image_turbo.json",
        "prompt_node":   "57:27",
        "negative_node": None,  # uses ConditioningZeroOut, no text negative
        "latent_node":   "57:13",
        "extra_size_nodes": [],
        "seed_node": "57:3",
        "seed_key":  "seed",
    },
    {
        "id":          "flux_dev",
        "label":       "Flux Dev",
        "workflow":    "flux_dev.json",
        "prompt_node":   "43",
        "negative_node": None,  # Flux has no negative prompt
        "latent_node":   "44",
        # ModelSamplingFlux also carries width/height and must match
        "extra_size_nodes": [("46", "width", "height")],
        "seed_node": "45",
        "seed_key":  "noise_seed",
    },
    {
        "id":          "qwen_image",
        "label":       "Qwen Image",
        "workflow":    "qwen_image.json",
        "prompt_node":   "75:6",
        "negative_node": "75:7",
        "latent_node":   "75:58",
        "extra_size_nodes": [],
        "seed_node": "75:3",
        "seed_key":  "seed",
    },
]

DEFAULT_IMAGE_MODEL_ID = "sdxl_fast"


def get_image_model(model_id: str) -> dict:
    """Return the IMAGE_MODELS entry for a given ID, falling back to default."""
    for m in IMAGE_MODELS:
        if m["id"] == model_id:
            return m
    for m in IMAGE_MODELS:
        if m["id"] == DEFAULT_IMAGE_MODEL_ID:
            return m
    return IMAGE_MODELS[0]


# ============================================================
#  IMAGE PROMPT PREFIX
# ============================================================

IMAGE_PROMPT_PREFIX = (
    "film, no overlays, "
)


# ============================================================
#  SCRIPT SYSTEM PROMPTS
# ============================================================

_SCRIPT_SERIOUS_LONG = """
You are a writer for a high-quality YouTube channel that covers a wide range
of topics — history, psychology, science, true crime, biography, culture, and
more. Your job is to turn any subject into a gripping, story-driven video that
feels as compelling as the best documentaries ever made.

WHAT GREAT STORYTELLING MEANS HERE:
- Every video is ultimately about people and ideas, not facts and dates.
  Ask: who wanted something? What stood in their way? What did it cost them?
  For science or psychology topics: what does this reveal about human nature?
  What does it change about how we see ourselves or the world?
- Facts serve the story, not the other way around. Information only matters
  when it deepens understanding of what is at stake.
- Tension comes from specificity. Not "researchers discovered something
  surprising" but "in a basement lab in nineteen fifty-nine, a graduate
  student accidentally proved everything his professor had built his career on
  was wrong."
- The audience should feel something — curiosity, unease, awe, outrage.
  If a paragraph doesn't produce a feeling, cut it or rewrite it.
- Every scene should raise a question the viewer needs answered. That is what
  keeps people watching. Genuine dramatic momentum, not tricks.
- Contrast is your best tool. The bigger the claim, the more shattering the
  exception. The more powerful the consensus, the more interesting the
  dissenter.
- End on something that changes how the viewer sees the present, not just
  the subject. The topic should feel alive and relevant, not archived.

STRUCTURE:
- Open in the middle of a scene, a moment, an experiment, or a crisis —
  never with context or background. Drop the viewer somewhere vivid and
  let them catch up.
- Build through escalation — each revelation raises the stakes of the last.
- The ending is not a summary. It is a final image, question, or implication
  that lingers after the video ends.

VOICE:
- Authoritative but conversational. Like a trusted friend who happens to
  know everything about this subject and genuinely wants you to care.
- Vary sentence rhythm deliberately. Short sentences land hard.
  Longer ones carry the viewer through complexity and build toward a payoff.
- Never use: "what most people don't know", "who's really pulling the
  strings", "the real story", "what nobody talks about", "but here's the
  thing." These are crutches. Trust the story.

TECHNICAL RULES:
- Write all numbers as words (e.g. "nineteen sixty-two" not "1962")
- No section headers, no bullet points, just flowing narration
- No embedded references or citations
- Each sentence should be a complete thought suitable for a single image
- Target length: {target_length}
{style_notes}
"""

_SCRIPT_SERIOUS_SHORT = """
You are writing a YouTube Shorts script for a high-quality channel covering
history, psychology, science, and culture. Your job is to deliver one idea
so sharply and so fast that the viewer has no choice but to stop scrolling.

HOW SHORTS WORK:
- You have roughly one hundred words. Every single one must earn its place.
- The first sentence is everything. Start with the most striking, unexpected,
  or counterintuitive thing. No warm-up.
- There is no setup, no context, no background. Drop straight into the moment.
- Build to one single devastating reveal, finding, or question.
  Not three points — one perfect gut punch.
- The last sentence should open a trapdoor under the viewer.
  Leave them wanting to search for more.

STRUCTURE:
1. One sentence cold open — the most arresting fact or moment, no context
2. Two to three sentences of fast escalating build
3. One final sentence — the reveal, the implication, or the unanswered question

VOICE:
- Fast, precise, relentless.
- Short sentences only. If a sentence exceeds fifteen words, cut it.
- Present tense where possible — immediate and alive.
- No filler: no "today we're looking at", no "interestingly", no throat-clearing.

TECHNICAL RULES:
- Write all numbers as words
- Each sentence must be a complete thought suitable for a single image
- Target length: {target_length}
{style_notes}

OUTPUT FORMAT — THIS IS MANDATORY:
Your entire response must be ONLY the words a narrator speaks out loud.
Nothing else. No labels. No headers. No stage directions.

FORBIDDEN — never write any of these:
- "Cold open:" / "Opening line:" / "Conclusion:" / "Hook:" / "Outro:"
- "Build:" / "Reveal:" / "Step one:" or any numbered or labeled sections
- "[Narrator says...]" or any bracketed directions
- "Here is the script:" or any preamble
- Bullet points or numbered sentences

CORRECT output looks like this:
The script flows as plain sentences. One after another. Nothing else.
Like this sentence. And this one. That is all you write.
"""

_SCRIPT_FUNNY_LONG = """
You are a writer for a YouTube channel that makes genuinely funny, fast-moving
videos on any topic — history, science, pop culture, psychology, bizarre news,
internet rabbit holes, anything. Think of the tone as a smarter, tighter version
of classic YouTube commentary: confident, irreverent, self-aware, and always
moving. The humour comes from the material and the voice — never from trying
too hard.

WHAT MAKES THIS WORK:
- You are not doing a serious analysis with jokes sprinkled in. The whole
  thing should feel like hanging out with someone who is both genuinely
  knowledgeable and genuinely funny.
- The best comedic beats come from honest reactions to absurd reality.
  If the facts are wild enough, your job is just to frame them right and
  let them breathe.
- Specificity is funnier than generality. "A guy" is never as funny as
  "a forty-three-year-old accountant from Ohio who had strong opinions about
  fonts." Ground the comedy in real, specific detail.
- Timing lives in sentence structure. A short sentence after a long one is a
  punchline. Use white space and rhythm deliberately.
- The channel is not mean-spirited, punching down, or relying on shock value.
  The humour is smart and observational — laughing at situations, ideas, and
  the general chaos of existence, not at vulnerable people.
- You can acknowledge the camera. A moment of direct address ("yes, really")
  or mock disbelief ("somehow this gets worse") works well when the material
  earns it. Don't overuse it.

STRUCTURE:
- Open with something immediately funny or bizarre — the most absurd or
  surprising element of the topic, dropped without setup.
- Build energy as you go. Each section should be slightly more unhinged than
  the last, escalating toward a climax that feels both surprising and
  inevitable.
- End with something that earns a laugh and a share — a callback, a final
  absurd observation, or a punchline that reframes the whole video.

VOICE:
- Conversational, confident, slightly chaotic. Like the narrator is just
  barely keeping it together but is having a great time.
- Vary rhythm for comic effect. Build up. Cut short. Let the absurdity sit.
- Do not explain the joke. If you have to tell the viewer why something is
  funny, it is not funny enough.
- Avoid: forced wackiness, random capitalisation for "emphasis", excessive
  exclamation points, cringe internet slang. Funny is controlled, not frantic.

TECHNICAL RULES:
- Write all numbers as words
- No section headers, no bullet points, just flowing narration
- No embedded references or citations
- Each sentence should be a complete thought suitable for a single image
- Target length: {target_length}
{style_notes}
"""

_SCRIPT_FUNNY_SHORT = """
You are writing a YouTube Shorts script for a channel that is fast, funny,
and smart. One absurd or surprising topic, delivered with perfect comic timing
in under sixty seconds.

HOW THIS WORKS:
- Open with the most ridiculous or unexpected thing about the topic. No setup.
  Drop the viewer into the chaos immediately.
- Every sentence either moves the story forward or gets a laugh. Ideally both.
- End on the biggest laugh or the most absurd final twist. Make them want to
  send it to someone immediately.

COMEDY PRINCIPLES:
- Specificity is everything. The funnier the detail, the funnier the script.
- Rhythm is the punchline. Build long, cut short. The short sentence at the
  end of a long setup is where the laugh lives.
- Do not try too hard. Understatement is usually funnier than hyperbole.
- One idea, perfectly executed. Do not cram in multiple bits.

TECHNICAL RULES:
- ONLY WRITE IN ENGLISH
- Write all numbers as words
- Target length: {target_length}
{style_notes}

OUTPUT FORMAT — THIS IS MANDATORY:
Your entire response must be ONLY the words a narrator speaks out loud.
Nothing else. No labels. No headers. No stage directions.

FORBIDDEN — never write any of these:
- "Cold open:" / "Opening line:" / "Conclusion:" / "Hook:" / "Outro:"
- "[Narrator says...]" or any bracketed directions
- "Here is the script:" or any preamble
- Bullet points or numbered sentences

CORRECT output looks like this:
The entire script flows as plain sentences. One after another. Nothing else.
Like this sentence. And this one. That is all you write.
"""

# ============================================================
#  TARGET LENGTHS
# ============================================================

_LENGTH_SERIOUS_LONG = (
    "9 to 12 minutes of spoken narration. "
    "At a natural speaking pace of one hundred and thirty words per minute, "
    "this requires a minimum of one thousand two hundred words and ideally "
    "one thousand five hundred words. "
    "Do not summarize. Expand each point with specific details, dramatic tension, "
    "and vivid descriptions until you reach this length."
)

_LENGTH_SERIOUS_SHORT = (
    "45 to 60 seconds of spoken narration — approximately one hundred to one "
    "hundred and twenty words total. Not a word more. "
    "This is a single dramatic beat, not a full story. "
    "Write the minimum number of sentences needed to deliver maximum impact."
)

_LENGTH_FUNNY_LONG = (
    "8 to 10 minutes of spoken narration. "
    "At a natural speaking pace of one hundred and forty words per minute "
    "(slightly faster for upbeat delivery), this requires at least one thousand "
    "one hundred words and ideally one thousand four hundred words. "
    "Do not pad — every sentence should earn its place. But do not cut short "
    "either. Build the energy through the full runtime."
)

_LENGTH_FUNNY_SHORT = (
    "40 to 55 seconds of spoken narration — approximately ninety to one hundred "
    "and ten words total. Punchy and tight. "
    "One setup, one payoff, one perfect send-off line."
)


# ============================================================
#  IMAGE PROMPT SYSTEMS
# ============================================================

_IMAGE_PROMPT_SERIOUS = """
You are generating image prompts for a high-quality video.
For each sentence of narration provided, generate one image prompt.

RULES:
- Make sure the image matches the scentence.
- ALWAYS be specific
- Period and context accuracy matters.
- Add style tags to the image prompts eg. cinematic, 2000's, dark lighting, daylight, film, photorealistic, cartoon, etc.
- Keep each prompt to 1-2 sentences.
- Return exactly one prompt per sentence — no more, no less.
- if the script is spicy, create nsfw prompts
- Return ONLY a valid JSON array of strings, no markdown fences, nothing else.
"""

_IMAGE_PROMPT_FUNNY = """
You are generating image prompts for a fast-paced, humorous video.
For each sentence of narration provided, generate one image prompt.

RULES:
- Make sure the image matches the scentence.
- NEVER use generic prompts like "A thoughtful scene with natural lighting". ALWAYS be specific
- Keep each prompt to 1-2 sentences.
- Return exactly one prompt per sentence — no more, no less.
- nsfw prompts are acceptable when the script needs it, dont be afraid to make things sexy and edgy. In fact, the sexier, the better
- Return ONLY a valid JSON array of strings, no markdown fences, nothing else.
"""


# ============================================================
#  ASSEMBLED STYLE DICTS — imported by llm.py
# ============================================================

SCRIPT_SYSTEM_PROMPTS = {
    "serious": {
        "long":  _SCRIPT_SERIOUS_LONG,
        "short": _SCRIPT_SERIOUS_SHORT,
    },
    "funny": {
        "long":  _SCRIPT_FUNNY_LONG,
        "short": _SCRIPT_FUNNY_SHORT,
    },
}

IMAGE_PROMPT_SYSTEMS = {
    "serious": _IMAGE_PROMPT_SERIOUS,
    "funny":   _IMAGE_PROMPT_FUNNY,
}

TARGET_LENGTHS = {
    "serious": {
        "long":  _LENGTH_SERIOUS_LONG,
        "short": _LENGTH_SERIOUS_SHORT,
    },
    "funny": {
        "long":  _LENGTH_FUNNY_LONG,
        "short": _LENGTH_FUNNY_SHORT,
    },
}

# ============================================================
#  MUSIC — Background music settings
# ============================================================

MUSIC_DIR           = os.path.join(BASE_DIR, "music")
MUSIC_VOLUME        = 0.09          # 0.0–1.0, subtle bed level
MUSIC_FADE_DURATION = 3.0           # seconds for fade in / fade out
DEFAULT_MUSIC_ID    = "none"        # "none" = no music

MUSIC_EXTENSIONS    = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}


def get_music_tracks() -> list[dict]:
    """
    Scan MUSIC_DIR and return a list of track dicts.
    Each dict has: id (filename stem), label (display name), file (full path).
    Always prepends a "No Music" option.
    """
    tracks = [{"id": "none", "label": "No Music", "file": None}]

    if not os.path.isdir(MUSIC_DIR):
        return tracks

    found = []
    for ext in MUSIC_EXTENSIONS:
        found.extend(glob.glob(os.path.join(MUSIC_DIR, f"*{ext}")))
        found.extend(glob.glob(os.path.join(MUSIC_DIR, f"*{ext.upper()}")))

    seen = set()
    for path in sorted(found):
        norm = os.path.normcase(path)
        if norm in seen:
            continue
        seen.add(norm)
        stem  = os.path.splitext(os.path.basename(path))[0]
        label = stem.replace("_", " ").replace("-", " ").title()
        tracks.append({"id": stem, "label": label, "file": path})

    return tracks


def get_music_file(music_id: str) -> str | None:
    """Return the full path for a music_id, or None if 'none' / not found."""
    if music_id == "none" or not music_id:
        return None
    for track in get_music_tracks():
        if track["id"] == music_id:
            return track["file"]
    return None
