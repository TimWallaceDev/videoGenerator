# ============================================================
#  LLM MODULE — Script + Image Prompt Generation
# ============================================================

import os
import re
import json
import subprocess
import requests
from config import (
    OLLAMA_MODEL, OLLAMA_BASE_URL,
    SCRIPT_SYSTEM_PROMPTS, IMAGE_PROMPT_SYSTEMS,
    TARGET_LENGTHS, SCRIPT_FILE,
)


def _chat(system: str, user: str) -> str:
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model":  OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
    }
    response = requests.post(url, json=payload, timeout=600)
    response.raise_for_status()
    return response.json()["message"]["content"].strip()


def split_into_sentences(text: str) -> list[str]:
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw if len(s.strip()) > 10]


def open_in_notepad(filepath: str):
    print(f"\n📝 Opening script in Notepad — edit freely, then save and close.\n")
    subprocess.run(["notepad.exe", filepath])


def generate_script(
    topic: str,
    auto:  bool = False,
    research: str = "",
    mode:  str = "long",
    style: str = "serious",
    style_notes: str = "",
) -> str:
    """
    Generate a narration script.
    style_notes: optional free-text modifier appended to the system prompt,
                 e.g. "focus on the psychological angle" or "suitable for kids".
    """
    print(f"✍️  Generating script for: '{topic}' [{style} / {mode}]...")

    system_template = SCRIPT_SYSTEM_PROMPTS[style][mode]
    target_length   = TARGET_LENGTHS[style][mode]

    # Format style_notes into the prompt placeholder
    notes_block = ""
    if style_notes and style_notes.strip():
        notes_block = f"\nADDITIONAL STYLE NOTES:\n{style_notes.strip()}\n"

    system = system_template.format(
        target_length=target_length,
        style_notes=notes_block,
    )

    if research:
        user = (
            f"Use the following research as your factual foundation. "
            f"Do not invent facts not supported by the research.\n\n"
            f"RESEARCH BRIEF:\n{research}\n\n"
            f"Now write a narration script about: {topic}"
        )
    else:
        user = f"Write a narration script about the following topic: {topic}"

    script = _chat(system, user)

    os.makedirs(os.path.dirname(SCRIPT_FILE), exist_ok=True)
    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(script)

    print(f"✅ Script generated ({len(script.split())} words)")

    if not auto:
        open_in_notepad(SCRIPT_FILE)
        with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
            script = f.read().strip()
        print("✅ Script accepted. Continuing...\n")

    return script


def generate_image_prompts(
    sentences: list[str],
    auto:  bool = False,
    style: str  = "serious",
) -> list[str]:
    BATCH_SIZE  = 10
    all_prompts = []
    batches     = [sentences[i:i+BATCH_SIZE] for i in range(0, len(sentences), BATCH_SIZE)]
    system      = IMAGE_PROMPT_SYSTEMS[style]

    print(f"🎨 Generating {len(sentences)} image prompts [{style}] in {len(batches)} batches...")

    for batch_num, batch in enumerate(batches, 1):
        print(f"   Batch {batch_num}/{len(batches)}...")
        numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(batch))
        user     = f"Generate one image prompt for each of these narration sentences:\n\n{numbered}"

        raw     = _chat(system, user)
        cleaned = re.sub(r"```json|```", "", raw).strip()

        try:
            prompts = json.loads(cleaned)
        except json.JSONDecodeError:
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
                prompts = [_fallback_prompt(style)] * len(batch)

        while len(prompts) < len(batch):
            prompts.append(_fallback_prompt(style))
        prompts = prompts[:len(batch)]
        all_prompts.extend(prompts)

    print(f"✅ Image prompts generated")

    if not auto:
        print("\n" + "="*60)
        print(f"IMAGE PROMPTS [{style.upper()}] — review before image generation:")
        print("="*60)
        for i, (sentence, prompt) in enumerate(zip(sentences, all_prompts), 1):
            print(f"\n[{i}] Narration : {sentence[:80]}")
            print(f"    Image    : {prompt}")
        print("\n" + "="*60)
        input("\nPress Enter to start image generation, or Ctrl+C to abort: ")

    return all_prompts


def _fallback_prompt(style: str) -> str:
    if style == "funny":
        return (
            "A confused-looking generic person in a mundane setting, "
            "deadpan composition, bright flat lighting, photorealistic."
        )
    return (
        "A thoughtful scene with natural lighting, cinematic composition, "
        "shallow depth of field, photorealistic."
    )