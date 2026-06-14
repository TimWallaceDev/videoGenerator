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
OLLAMA_MODEL    = "llama3.1:8b"
OLLAMA_BASE_URL = "http://localhost:11434"

# --- ComfyUI ---
COMFYUI_URL     = "http://localhost:8188"
CHATTERBOX_WORKFLOW = os.path.join(WORKFLOWS_DIR, "chatterbox.json")
IMAGEGEN_WORKFLOW   = os.path.join(WORKFLOWS_DIR, "imagegen.json")

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
    # Fallback to default
    for v in VOICES:
        if v["id"] == DEFAULT_VOICE_ID:
            return v["file"]
    return VOICES[0]["file"]


# ============================================================
#  IMAGE PROMPT PREFIX
# ============================================================

IMAGE_PROMPT_PREFIX = (
    "cinematic photography, high detail, "
    "no text, no letters, no words, no signs, no writing, no typography, "
    "no watermarks, no overlays, "
)


# ============================================================
#  SCRIPT SYSTEM PROMPTS
# ============================================================

_SCRIPT_SERIOUS_LONG = """
You are a writer for a high-quality Video Production company that covers a wide range
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
- No section headers, no bullet points, just flowing narration
- Each sentence must be a complete thought suitable for a single image
- Target length: {target_length}
{style_notes}
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
- Write all numbers as words
- No section headers, no bullet points, just flowing narration
- Each sentence must be a complete thought suitable for a single image
- Target length: {target_length}
{style_notes}
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
    "20 to 40 seconds of spoken narration — approximately one hundred to one "
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
    "20 to 40 seconds of spoken narration — approximately ninety to one hundred "
    "and ten words total. Punchy and tight. "
    "One setup, one payoff, one perfect send-off line."
)


# ============================================================
#  IMAGE PROMPT SYSTEMS
# ============================================================

_IMAGE_PROMPT_SERIOUS = """
You are generating image prompts for a high-quality YouTube video.
For each sentence of narration provided, generate one image prompt.

RULES:
- NO TEXT of any kind — no signs, no readable text, no chalkboards,
  no newspapers with legible words, no storefronts with writing.
- Match the emotional register of the narration precisely.
  Loss: muted tones, empty space, long shadows.
  Discovery: bright light, open space, movement.
  Power: dramatic architecture, high contrast, low angle.
  Dread: tight framing, darkness at the edges, stillness.
- Think like a cinematographer. Describe light source, camera angle,
  depth of field, and mood — not just subject matter.
- Period and context accuracy matters.
- Never reference real named people, specific real locations by name,
  or copyrighted material.
- Keep each prompt to 1-2 sentences.
- Return exactly one prompt per sentence — no more, no less.
- Return ONLY a valid JSON array of strings, no markdown fences, nothing else.

Example:
["Close-up of weathered hands gripping a worn leather journal, shallow depth of field, warm candlelight, photorealistic", "Wide shot of an empty brutalist government corridor at night, single overhead light, long shadows, 35mm grain"]

NEVER USE THIS PROMPT OR ANYTHING SIMILAR:  A confused-looking generic person in a mundane setting, deadpan composition, bright flat lighting, photorealistic.

"""

_IMAGE_PROMPT_FUNNY = """
You are generating image prompts for a fast-paced, humorous YouTube video.
For each sentence of narration provided, generate one image prompt.

RULES:
- NO TEXT of any kind — no signs, no readable text, no labels, nothing.
- Match the comedic energy of the narration. Absurd situations get absurd
  framing. Understated jokes get deadpan, clinical composition.
- Think like a comedy director. A close-up on a single ridiculous detail is
  often funnier than a wide establishing shot.
- Lean into unexpected angles and bathetic contrasts — the mundane presented
  with the grandeur of an epic, or the important presented undignified.
- No real people, no named locations, no copyrighted material.
- Keep each prompt to 1-2 sentences.
- Return exactly one prompt per sentence — no more, no less.
- Return ONLY a valid JSON array of strings, no markdown fences, nothing else.

Example:
["A man in an ill-fitting suit staring blankly at an enormous stack of paper taller than he is, fluorescent office lighting, deadpan wide shot", "Extreme close-up of a single wilting houseplant on an otherwise empty conference table, harsh overhead light, photorealistic"]

NEVER USE THIS PROMPT OR ANYTHING SIMILAR:  A confused-looking generic person in a mundane setting, deadpan composition, bright flat lighting, photorealistic. 
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
#  Add this block to the bottom of config.py
# ============================================================

MUSIC_DIR           = os.path.join(BASE_DIR, "music")
MUSIC_VOLUME        = 0.09          # 0.0–1.0, subtle bed level
MUSIC_FADE_DURATION = 3.0           # seconds for fade in / fade out
DEFAULT_MUSIC_ID    = "none"        # "none" = no music

# Supported audio formats for music files
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

    # Sort alphabetically, deduplicate
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