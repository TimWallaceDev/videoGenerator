# ============================================================
#  TRANSCRIBE MODULE — Whisper via faster-whisper
#  Transcribes the generated audio and matches word-level
#  timestamps to the ORIGINAL SCRIPT SENTENCES so that
#  image count always matches timestamp count exactly.
# ============================================================

import os
import re
import json
from faster_whisper import WhisperModel
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
from config import (
    AUDIO_FILE,
    TIMESTAMPS_FILE,
    WORDS_FILE,
    SCRIPT_FILE,
    TEMP_DIR,
)
from status import pipeline_status

WHISPER_MODEL_SIZE = "medium"


def _unload_model(model: WhisperModel):
    """
    Explicitly delete the Whisper model and flush VRAM.
    Faster-Whisper holds GPU memory until garbage collected.
    """
    del model
    if TORCH_AVAILABLE:
        torch.cuda.empty_cache()
    print("   🧹 Whisper model unloaded from VRAM")
WHISPER_DEVICE     = "cuda"
WHISPER_COMPUTE    = "float16"


# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------

def _load_model() -> WhisperModel:
    pipeline_status.update("Transcription", 4, "Loading Whisper model...", 55)
    print(f"   Loading Whisper {WHISPER_MODEL_SIZE} on {WHISPER_DEVICE}...")
    return WhisperModel(
        WHISPER_MODEL_SIZE,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE
    )


def _clean(text: str) -> str:
    """Lowercase, strip punctuation and extra whitespace for fuzzy matching."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_all_words(segments) -> list[dict]:
    """Extract all word-level timestamps from Whisper segments."""
    words = []
    for segment in segments:
        if hasattr(segment, "words") and segment.words:
            for word in segment.words:
                words.append({
                    "word":  word.word.strip(),
                    "start": word.start,
                    "end":   word.end,
                })
    return words


def _match_sentences_to_words(
    script_sentences: list[str],
    words: list[dict],
) -> list[dict]:
    """
    Match each script sentence to word-level timestamps from Whisper.

    Strategy:
    - Clean both script sentences and Whisper words for fuzzy matching
    - Walk through words sequentially, consuming words that match
      the first word of the next script sentence
    - This handles Whisper slightly mishearing words (e.g. "18th" vs
      "eighteenth") by falling back to positional alignment if needed

    Returns a list of timestamp dicts matching script_sentences length.
    """
    results     = []
    word_idx    = 0
    total_words = len(words)

    for sent_idx, sentence in enumerate(script_sentences):
        sent_words   = _clean(sentence).split()
        n_sent_words = len(sent_words)

        if word_idx >= total_words:
            # Ran out of words — use last known timestamp
            last_end = words[-1]["end"] if words else 0
            results.append({
                "start": round(last_end, 3),
                "end":   round(last_end, 3),
                "text":  sentence,
            })
            continue

        # Record start of this sentence
        start_time = words[word_idx]["start"]

        # Try to find the first word of this sentence in the next few words
        # (handles Whisper inserting filler words)
        if sent_words:
            first_word = sent_words[0]
            for lookahead in range(min(5, total_words - word_idx)):
                if _clean(words[word_idx + lookahead]["word"]) == first_word:
                    word_idx   += lookahead
                    start_time  = words[word_idx]["start"]
                    break

        # Advance word_idx by the number of words in this sentence
        end_word_idx = min(word_idx + n_sent_words - 1, total_words - 1)
        end_time     = words[end_word_idx]["end"]

        results.append({
            "start": round(start_time, 3),
            "end":   round(end_time, 3),
            "text":  sentence,
        })

        word_idx += n_sent_words

    return results


def _load_script_sentences() -> list[str]:
    """
    Load the original script sentences from SCRIPT_FILE.
    Falls back to None if file doesn't exist.
    """
    if not os.path.exists(SCRIPT_FILE):
        return None

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        script = f.read().strip()

    raw = re.split(r'(?<=[.!?])\s+', script)
    sentences = [s.strip() for s in raw if len(s.strip()) > 10]
    return sentences


# ------------------------------------------------------------
#  Main function
# ------------------------------------------------------------

def transcribe_audio(
    audio_path: str = None,
    script_sentences: list[str] = None,
) -> list[dict]:
    """
    Transcribe the audio file and match timestamps to script sentences.

    If script_sentences is provided (or SCRIPT_FILE exists), timestamps
    are matched to the original script — guaranteeing the count matches
    the number of images generated.

    If no script is available, falls back to Whisper's own sentence
    detection (original behaviour).

    Returns list of {"start", "end", "text"} dicts.
    """
    if audio_path is None:
        audio_path = AUDIO_FILE

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Load script sentences if not passed in
    if script_sentences is None:
        script_sentences = _load_script_sentences()

    if script_sentences:
        print(f"🎧 Transcribing audio (matching to {len(script_sentences)} script sentences)...")
    else:
        print(f"🎧 Transcribing audio (no script found, using Whisper sentences)...")

    pipeline_status.update("Transcription", 4, "Transcribing audio...", 55)

    model = _load_model()

    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        language="en",
        beam_size=5,
    )

    print(f"   Detected language: {info.language} "
          f"(confidence: {info.language_probability:.0%})")
    print(f"   Duration: {info.duration:.1f}s")

    pipeline_status.update("Transcription", 4,
                           f"Processing {info.duration:.0f}s of audio...", 57)

    segments_list = list(segments)
    words         = _get_all_words(segments_list)

    if not words:
        raise RuntimeError("Whisper returned no word-level timestamps. "
                           "Make sure the audio file is valid.")

    print(f"   Words detected: {len(words)}")

    # Save word-level timestamps for caption generation
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=2, ensure_ascii=False)

    if script_sentences:
        # Primary path — match to original script sentences
        sentences = _match_sentences_to_words(script_sentences, words)
        print(f"   Matched to {len(sentences)} script sentences ✓")
    else:
        # Fallback — use Whisper's own sentence detection
        full_text     = " ".join(w["word"] for w in words)
        raw_sentences = re.split(r'(?<=[.!?])\s+', full_text.strip())
        raw_sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 5]
        sentences     = _match_sentences_to_words(raw_sentences, words)
        print(f"   Detected {len(sentences)} sentences (Whisper fallback)")

    # Unload model to free VRAM for image generation
    _unload_model(model)

    pipeline_status.update("Transcription", 4,
                           f"Matched {len(sentences)} sentences", 59)

    # Save to file
    os.makedirs(TEMP_DIR, exist_ok=True)
    with open(TIMESTAMPS_FILE, "w", encoding="utf-8") as f:
        json.dump(sentences, f, indent=2, ensure_ascii=False)

    print(f"✅ Timestamps saved to {TIMESTAMPS_FILE}")

    # Preview first few
    print("\n   Preview:")
    for entry in sentences[:4]:
        print(f"   [{entry['start']:6.2f}s] {entry['text'][:70]}")
    if len(sentences) > 4:
        print(f"   ... and {len(sentences) - 4} more")

    return sentences


# ------------------------------------------------------------
#  Entry point for isolated testing
# ------------------------------------------------------------

if __name__ == "__main__":
    print("🧪 Testing transcribe module...")
    sentences = transcribe_audio()

    print(f"\n✅ Transcribe test complete.")
    print(f"   Found {len(sentences)} sentences")
    print(f"\nFull timestamp data:")
    for i, entry in enumerate(sentences, 1):
        print(f"   [{i:2d}] {entry['start']:6.2f}s - {entry['end']:6.2f}s | {entry['text'][:60]}")