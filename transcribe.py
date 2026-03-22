# ============================================================
#  TRANSCRIBE MODULE — Whisper via faster-whisper
#  Transcribes the generated audio and extracts sentence-level
#  timestamps to drive image switching in the final video.
# ============================================================

import os
import json
import re
from faster_whisper import WhisperModel
from config import (
    AUDIO_FILE,
    TIMESTAMPS_FILE,
    TEMP_DIR,
)
from status import pipeline_status

# Whisper model size — "medium" is the sweet spot for accuracy vs speed
# Options: tiny, base, small, medium, large-v2, large-v3
WHISPER_MODEL_SIZE = "medium"

# Device to run on — "cuda" uses your 4090, "cpu" as fallback
WHISPER_DEVICE     = "cuda"
WHISPER_COMPUTE    = "float16"  # float16 for GPU, int8 for CPU


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


def _segments_to_sentences(segments) -> list[dict]:
    """
    Convert Whisper word-level segments into sentence-level timestamps.
    Each sentence gets a start time (when to switch to its image).

    Returns a list of dicts:
    [
        {"start": 0.0, "end": 4.2, "text": "Sentence one here."},
        {"start": 4.2, "end": 9.1, "text": "Sentence two here."},
        ...
    ]
    """
    # Collect all words with timestamps
    words = []
    for segment in segments:
        if hasattr(segment, "words") and segment.words:
            for word in segment.words:
                words.append({
                    "word":  word.word,
                    "start": word.start,
                    "end":   word.end,
                })

    if not words:
        raise RuntimeError("Whisper returned no word-level timestamps. "
                           "Make sure the audio file is valid.")

    # Reconstruct full text and split into sentences
    full_text = " ".join(w["word"].strip() for w in words)
    raw_sentences = re.split(r'(?<=[.!?])\s+', full_text.strip())
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 5]

    # Walk through words matching them to sentences
    sentence_timestamps = []
    word_idx = 0

    for sentence in sentences:
        sentence_words = sentence.split()
        word_count = len(sentence_words)

        if word_idx >= len(words):
            break

        start_time = words[word_idx]["start"]

        end_idx = min(word_idx + word_count - 1, len(words) - 1)
        end_time = words[end_idx]["end"]

        sentence_timestamps.append({
            "start": round(start_time, 3),
            "end":   round(end_time, 3),
            "text":  sentence,
        })

        word_idx += word_count

    return sentence_timestamps


# ------------------------------------------------------------
#  Main function
# ------------------------------------------------------------

def transcribe_audio(audio_path: str = None) -> list[dict]:
    """
    Transcribe the audio file and extract sentence-level timestamps.
    Saves results to TIMESTAMPS_FILE and returns the list.

    Each entry: {"start": float, "end": float, "text": str}
    """
    if audio_path is None:
        audio_path = AUDIO_FILE

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    pipeline_status.update("Transcription", 4, "Transcribing audio...", 55)
    print(f"🎧 Transcribing audio: {os.path.basename(audio_path)}")

    model = _load_model()

    # Transcribe with word-level timestamps
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

    # Convert generator to list (required before processing)
    segments_list = list(segments)
    print(f"   Segments: {len(segments_list)}")

    sentences = _segments_to_sentences(segments_list)

    pipeline_status.update("Transcription", 4,
                           f"Found {len(sentences)} sentences", 59)
    print(f"   Sentences with timestamps: {len(sentences)}")

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