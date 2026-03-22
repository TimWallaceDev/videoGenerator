# ============================================================
#  TTS MODULE — Chatterbox via ComfyUI
#  Splits script into chunks, generates audio for each,
#  then stitches them together into a single audio file.
# ============================================================

import os
import re
import json
import time
import copy
import uuid
import shutil
import requests
import websocket
import subprocess
from config import (
    COMFYUI_URL,
    CHATTERBOX_WORKFLOW,
    AUDIO_FILE,
    TEMP_DIR,
    FFMPEG,
    FFPROBE
)
from status import pipeline_status

# Chatterbox hard limit per generation (characters)
# Slightly under 4000 to be safe
CHATTERBOX_CHAR_LIMIT = 1000

# Node IDs in the workflow (matching your exported JSON)
NODE_TTS       = "1"   # ChatterboxTTS
NODE_SAVE      = "2"   # SaveAudioMP3
NODE_LOADAUDIO = "4"   # LoadAudio (voice reference)


# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------

def _load_workflow() -> dict:
    with open(CHATTERBOX_WORKFLOW, "r", encoding="utf-8") as f:
        return json.load(f)


def _chunk_script(script: str) -> list[str]:
    """
    Split script into chunks that fit within Chatterbox's character limit.
    Splits on sentence boundaries to avoid cutting mid-sentence.
    """
    sentences = re.split(r'(?<=[.!?])\s+', script.strip())
    chunks = []
    current = ""

    for sentence in sentences:
        candidate = (current + " " + sentence).strip()
        if len(candidate) <= CHATTERBOX_CHAR_LIMIT:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    return chunks


def _get_widget_names(node_type: str) -> list[str]:
    """
    Map node type to ordered widget parameter names.
    Order matches widgets_values array in the exported workflow JSON.
    Derived from /object_info endpoint.
    """
    widget_map = {
        "ChatterboxTTS": [
            "model_pack_name",    # 0 - "resembleai_default_voice"
            "text",               # 1 - script text (we inject this)
            "max_new_tokens",     # 2 - 4000
            "flow_cfg_scale",     # 3 - 0.7
            "exaggeration",       # 4 - 0.5
            "temperature",        # 5 - 0.8
            "cfg_weight",         # 6 - 0.5
            "repetition_penalty", # 7 - 1.2
            "min_p",              # 8 - 0.05
            "top_p",              # 9 - 1.0
            "seed",               # 10 - random int
            "use_watermark",      # 11 - false
        ],
        "SaveAudioMP3": [
            "filename_prefix",    # 0 - output filename
            "quality",            # 1 - "V0"
        ],
        "LoadAudio": [
            "audio",              # 0 - filename in ComfyUI input folder
        ],
    }
    return widget_map.get(node_type, [f"param_{i}" for i in range(20)])


def _build_api_workflow(workflow: dict) -> dict:
    """
    Convert ComfyUI's visual node-list format into the API dict format
    that the /prompt endpoint expects.
    """
    api_workflow = {}

    # First pass: build nodes with widget values
    for node in workflow["nodes"]:
        node_id   = str(node["id"])
        node_type = node["type"]

        api_workflow[node_id] = {
            "class_type": node_type,
            "inputs": {}
        }

        if "widgets_values" in node:
            widget_names = _get_widget_names(node_type)
            for idx, val in enumerate(node["widgets_values"]):
                if idx < len(widget_names):
                    api_workflow[node_id]["inputs"][widget_names[idx]] = val

        # LoadAudio: the audio input is the filename string, not a node link
        if node_type == "LoadAudio":
            api_workflow[node_id]["inputs"]["audio"] = node["widgets_values"][0]

    # Second pass: wire up links between nodes
    for link in workflow.get("links", []):
        # link format: [link_id, src_node_id, src_slot, dst_node_id, dst_slot, type]
        _, src_node, src_slot, dst_node, dst_slot, _ = link
        dst_node_id = str(dst_node)

        # Find the input name for dst_slot on the destination node
        for node in workflow["nodes"]:
            if str(node["id"]) == dst_node_id:
                node_inputs = node.get("inputs", [])
                if dst_slot < len(node_inputs):
                    input_name = node_inputs[dst_slot]["name"]
                    api_workflow[dst_node_id]["inputs"][input_name] = [str(src_node), src_slot]
                break

    return api_workflow


def _queue_prompt(api_workflow: dict) -> tuple[str, str]:
    """Submit a workflow to ComfyUI and return (prompt_id, client_id)."""
    client_id = str(uuid.uuid4())
    payload   = {"prompt": api_workflow, "client_id": client_id}
    response  = requests.post(f"{COMFYUI_URL}/prompt", json=payload)
    response.raise_for_status()
    return response.json()["prompt_id"], client_id


def _wait_for_completion(prompt_id: str, client_id: str, timeout: int = 300):
    """
    Wait for ComfyUI to finish executing the prompt.
    Tries WebSocket first, falls back to polling history if connection drops.
    """
    ws_url = f"{COMFYUI_URL.replace('http', 'ws')}/ws?clientId={client_id}"

    try:
        ws = websocket.create_connection(ws_url, timeout=30)
        try:
            start = time.time()
            while True:
                if time.time() - start > timeout:
                    raise TimeoutError(f"Timed out after {timeout}s")
                msg = json.loads(ws.recv())
                if msg.get("type") == "executing":
                    data = msg.get("data", {})
                    if data.get("node") is None and data.get("prompt_id") == prompt_id:
                        return
        finally:
            ws.close()

    except (ConnectionResetError, ConnectionRefusedError,
            websocket.WebSocketConnectionClosedException,
            websocket.WebSocketTimeoutException, OSError):
        # WebSocket dropped — fall back to polling history endpoint
        print("   ⚠️  WebSocket dropped, falling back to polling...")
        _poll_until_complete(prompt_id, timeout=600)


def _poll_until_complete(prompt_id: str, timeout: int = 600):
    """Poll the history endpoint until the prompt appears as completed."""
    start = time.time()
    while True:
        if time.time() - start > timeout:
            raise TimeoutError(f"Polling timed out after {timeout}s")

        try:
            response = requests.get(
                f"{COMFYUI_URL}/history/{prompt_id}", timeout=10
            )
            history = response.json()
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                if outputs:
                    return  # Job finished
        except requests.RequestException:
            pass  # ComfyUI briefly unavailable, keep polling

        time.sleep(3)


def _get_output_filename(prompt_id: str) -> tuple[str, str]:
    """
    Poll ComfyUI history to get the output filename for a completed prompt.
    Returns (filename, subfolder).
    """
    for _ in range(10):
        response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
        history  = response.json()

        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            for node_id, node_output in outputs.items():
                if "audio" in node_output:
                    audio_info = node_output["audio"][0]
                    return audio_info["filename"], audio_info.get("subfolder", "")

        time.sleep(1)

    raise RuntimeError(f"Could not find output for prompt {prompt_id}")


def _download_audio(filename: str, subfolder: str, dest_path: str):
    """Download a generated audio file from ComfyUI to dest_path."""
    params = {"filename": filename, "type": "output"}
    if subfolder:
        params["subfolder"] = subfolder

    response = requests.get(f"{COMFYUI_URL}/view", params=params)
    response.raise_for_status()

    with open(dest_path, "wb") as f:
        f.write(response.content)


def _stitch_audio_files(chunk_paths: list[str], output_path: str):
    """Use ffmpeg to concatenate multiple audio files into one."""
    if len(chunk_paths) == 1:
        shutil.copy(chunk_paths[0], output_path)
        return

    list_file = os.path.join(TEMP_DIR, "audio_chunks.txt")
    with open(list_file, "w") as f:
        for path in chunk_paths:
            f.write(f"file '{path.replace(os.sep, '/')}'\n")

    subprocess.run([
        FFMPEG, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path
    ], check=True, capture_output=True)

    os.remove(list_file)


# ------------------------------------------------------------
#  Main function
# ------------------------------------------------------------

def generate_audio(script: str) -> str:
    """
    Generate audio for the full script using Chatterbox via ComfyUI.
    Splits into chunks if needed, stitches results into AUDIO_FILE.
    Returns path to the final audio file.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)

    chunks = _chunk_script(script)
    total  = len(chunks)
    print(f"🎙️  Generating audio in {total} chunk(s)...")

    base_workflow = _load_workflow()
    chunk_paths   = []

    for i, chunk in enumerate(chunks, 1):
        pipeline_status.update("Audio", 3, f"Chunk {i}/{total}...", 40)
        print(f"   Chunk {i}/{total} ({len(chunk)} chars)...")

        workflow = copy.deepcopy(base_workflow)

        # Inject script text into ChatterboxTTS node
        for node in workflow["nodes"]:
            if str(node["id"]) == NODE_TTS:
                node["widgets_values"][1] = chunk
                break

        # Set chunk-specific output filename
        for node in workflow["nodes"]:
            if str(node["id"]) == NODE_SAVE:
                node["widgets_values"][0] = f"audio/chunk_{i:03d}"
                break

        api_workflow = _build_api_workflow(workflow)

        prompt_id, client_id = _queue_prompt(api_workflow)
        _wait_for_completion(prompt_id, client_id)

        filename, subfolder = _get_output_filename(prompt_id)
        chunk_path = os.path.join(TEMP_DIR, f"chunk_{i:03d}.mp3")
        _download_audio(filename, subfolder, chunk_path)
        chunk_paths.append(chunk_path)
        print(f"   ✅ Chunk {i} done")

    pipeline_status.update("Audio", 3, "Stitching chunks...", 50)
    print("🔗 Stitching audio chunks...")
    _stitch_audio_files(chunk_paths, AUDIO_FILE)

    for path in chunk_paths:
        if os.path.exists(path):
            os.remove(path)

    print(f"✅ Audio saved to {AUDIO_FILE}")
    return AUDIO_FILE


# ------------------------------------------------------------
#  Entry point for isolated testing
# ------------------------------------------------------------

if __name__ == "__main__":
    test_script = (
        "Scarborough has been a part of Toronto's landscape since time immemorial, "
        "with Indigenous peoples having deep connections to the land. "
        "When European settlers arrived in the eighteenth century, they found this "
        "area rich with natural resources and abundant wildlife."
    )

    print("🧪 Testing TTS module...")
    audio_path = generate_audio(test_script)
    print(f"\n✅ TTS test complete. Audio at: {audio_path}")