# ============================================================
#  LLM MODULE — Script + Image Prompt Generation
#  Uses Ollama running locally on port 11434
# ============================================================

import os
import re
import json
import subprocess
import requests
from config import (
    OLLAMA_MODEL, OLLAMA_BASE_URL,
    SCRIPT_SYSTEM_PROMPT, IMAGE_PROMPT_SYSTEM,
    SCRIPT_FILE, TARGET_VIDEO_LENGTH
)


# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------

def _chat(system: str, user: str) -> str:
    """Send a single prompt to Ollama and return the response text."""
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ]
    }
    response = requests.post(url, json=payload, timeout=600)
    response.raise_for_status()
    return response.json()["message"]["content"].strip()


def split_into_sentences(text: str) -> list[str]:
    """Split script text into individual sentences."""
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in raw if len(s.strip()) > 10]
    return sentences


def open_in_notepad(filepath: str):
    """Open a file in Notepad and wait for the user to close it."""
    print(f"\n📝 Opening script in Notepad — edit freely, then save and close Notepad to continue.\n")
    subprocess.run(["notepad.exe", filepath])


# ------------------------------------------------------------
#  Main functions
# ------------------------------------------------------------

def generate_script(topic: str, auto: bool = False, research: str = "") -> str:
    """
    Generate a narration script for the given topic.
    If auto is False, opens the script in Notepad for review/editing.
    Returns the final script text.
    """
    print(f"✍️  Generating script for: '{topic}'...")

    system = SCRIPT_SYSTEM_PROMPT.format(target_length=TARGET_VIDEO_LENGTH)

    if research:
        user = (
            f"Use the following research as your factual foundation. "
            f"Do not invent facts not supported by the research."
            f"RESEARCH BRIEF:{research}"
            f"Now write a narration script about: {topic}"
        )
    else:
        user = f"Write a narration script about the following topic: {topic}"

    script = _chat(system, user)

    # Save to temp file
    os.makedirs(os.path.dirname(SCRIPT_FILE), exist_ok=True)
    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(script)

    print(f"✅ Script generated ({len(script.split())} words)")

    # Checkpoint — open in Notepad for review
    if not auto:
        open_in_notepad(SCRIPT_FILE)
        with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
            script = f.read().strip()
        print("✅ Script accepted. Continuing...\n")

    return script


def generate_image_prompts(sentences: list[str], auto: bool = False) -> list[str]:
    """
    Generate one image generation prompt per sentence.
    Processes in batches to avoid JSON errors on long scripts.
    If auto is False, displays prompts for review before continuing.
    """
    BATCH_SIZE = 10
    all_prompts = []
    batches = [sentences[i:i+BATCH_SIZE] for i in range(0, len(sentences), BATCH_SIZE)]

    print(f"🎨 Generating {len(sentences)} image prompts in {len(batches)} batches...")

    for batch_num, batch in enumerate(batches, 1):
        print(f"   Batch {batch_num}/{len(batches)}...")
        numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(batch))
        user = f"Generate one image prompt for each of these narration sentences:\n\n{numbered}"

        raw     = _chat(IMAGE_PROMPT_SYSTEM, user)
        cleaned = re.sub(r"```json|```", "", raw).strip()

        try:
            prompts = json.loads(cleaned)
        except json.JSONDecodeError:
            # Model returned one array per line instead of one big array
            try:
                prompts = []
                for line in cleaned.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    parsed = json.loads(line)
                    if isinstance(parsed, list):
                        prompts.extend(parsed)
                    elif isinstance(parsed, str):
                        prompts.append(parsed)
            except json.JSONDecodeError:
                print(f"   ⚠️  Batch {batch_num} failed to parse, using fallback prompts")
                prompts = ["A documentary-style historical scene, cinematic lighting, photorealistic."] * len(batch)

        # Ensure correct count for this batch
        while len(prompts) < len(batch):
            prompts.append("A documentary-style historical scene, cinematic lighting, photorealistic.")
        prompts = prompts[:len(batch)]

        all_prompts.extend(prompts)

    print(f"✅ Image prompts generated")

    # Checkpoint — show prompts for review
    if not auto:
        print("\n" + "="*60)
        print("IMAGE PROMPTS — review before image generation begins:")
        print("="*60)
        for i, (sentence, prompt) in enumerate(zip(sentences, all_prompts), 1):
            print(f"\n[{i}] Narration : {sentence[:80]}")
            print(f"    Image    : {prompt}")
        print("\n" + "="*60)
        input("\nPress Enter to start image generation, or Ctrl+C to abort: ")

    return all_prompts


# ------------------------------------------------------------
#  Entry point for isolated testing
# ------------------------------------------------------------

if __name__ == "__main__":
    test_topic = "The Avro Arrow — how Canada built the world's most advanced fighter jet"

    script    = generate_script(test_topic, auto=False)
    sentences = split_into_sentences(script)
    prompts   = generate_image_prompts(sentences, auto=False)

    print(f"\n✅ LLM module test complete.")
    print(f"   Script   : {len(script.split())} words")
    print(f"   Sentences: {len(sentences)}")
    print(f"   Prompts  : {len(prompts)}")