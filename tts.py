# ============================================================
#  TTS MODULE — Chatterbox via ComfyUI
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
    FFPROBE,
    DEFAULT_VOICE_ID,
    get_voice_file,
)
from status import pipeline_status

CHATTERBOX_CHAR_LIMIT = 1000

NODE_TTS       = "1"
NODE_SAVE      = "2"
NODE_LOADAUDIO = "4"


# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------

def _free_comfyui_memory():
    try:
        requests.post(f"{COMFYUI_URL}/free", json={
            "unload_models": True,
            "free_memory":   True,
        }, timeout=10)
        print("   🧹 ComfyUI VRAM freed after TTS")
    except requests.RequestException:
        pass


def _load_workflow() -> dict:
    with open(CHATTERBOX_WORKFLOW, "r", encoding="utf-8") as f:
        return json.load(f)


def _chunk_script(script: str) -> list[str]:
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
    widget_map = {
        "ChatterboxTTS": [
            "model_pack_name", "text", "max_new_tokens",
            "flow_cfg_scale", "exaggeration", "temperature",
            "cfg_weight", "repetition_penalty", "min_p", "top_p",
            "seed", "use_watermark",
        ],
        "SaveAudioMP3": ["filename_prefix", "quality"],
        "LoadAudio":    ["audio"],
    }
    return widget_map.get(node_type, [f"param_{i}" for i in range(20)])


def _build_api_workflow(workflow: dict) -> dict:
    api_workflow = {}

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

        if node_type == "LoadAudio":
            api_workflow[node_id]["inputs"]["audio"] = node["widgets_values"][0]

    for link in workflow.get("links", []):
        _, src_node, src_slot, dst_node, dst_slot, _ = link
        dst_node_id = str(dst_node)

        for node in workflow["nodes"]:
            if str(node["id"]) == dst_node_id:
                node_inputs = node.get("inputs", [])
                if dst_slot < len(node_inputs):
                    input_name = node_inputs[dst_slot]["name"]
                    api_workflow[dst_node_id]["inputs"][input_name] = [str(src_node), src_slot]
                break

    return api_workflow


def _queue_prompt(api_workflow: dict) -> tuple[str, str]:
    client_id = str(uuid.uuid4())
    payload   = {"prompt": api_workflow, "client_id": client_id}
    response  = requests.post(f"{COMFYUI_URL}/prompt", json=payload)
    response.raise_for_status()
    return response.json()["prompt_id"], client_id


def _wait_for_completion(prompt_id: str, client_id: str, timeout: int = 300):
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
        print("   ⚠️  WebSocket dropped, falling back to polling...")
        _poll_until_complete(prompt_id, timeout=600)


def _poll_until_complete(prompt_id: str, timeout: int = 600):
    start = time.time()
    while True:
        if time.time() - start > timeout:
            raise TimeoutError(f"Polling timed out after {timeout}s")
        try:
            response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            history  = response.json()
            if prompt_id in history:
                if history[prompt_id].get("outputs", {}):
                    return
        except requests.RequestException:
            pass
        time.sleep(3)


def _get_output_filename(prompt_id: str) -> tuple[str, str]:
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
    params = {"filename": filename, "type": "output"}
    if subfolder:
        params["subfolder"] = subfolder
    response = requests.get(f"{COMFYUI_URL}/view", params=params)
    response.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(response.content)


def _stitch_audio_files(chunk_paths: list[str], output_path: str):
    if len(chunk_paths) == 1:
        shutil.copy(chunk_paths[0], output_path)
        return

    list_file = os.path.join(TEMP_DIR, "audio_chunks.txt")
    with open(list_file, "w") as f:
        for path in chunk_paths:
            f.write(f"file '{path.replace(os.sep, '/')}'\n")

    subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", output_path
    ], check=True, capture_output=True)

    os.remove(list_file)


# ------------------------------------------------------------
#  Main function
# ------------------------------------------------------------

def generate_audio(script: str, voice_id: str = None) -> str:
    """
    Generate audio for the full script using Chatterbox via ComfyUI.
    voice_id: one of the IDs defined in config.VOICES.
              Defaults to DEFAULT_VOICE_ID if not specified.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)

    voice_file = get_voice_file(voice_id or DEFAULT_VOICE_ID)
    chunks     = _chunk_script(script)
    total      = len(chunks)

    print(f"🎙️  Generating audio in {total} chunk(s) [voice: {voice_file}]...")

    base_workflow = _load_workflow()
    chunk_paths   = []

    for i, chunk in enumerate(chunks, 1):
        pipeline_status.update("Audio", 3, f"Chunk {i}/{total}...", 40)
        print(f"   Chunk {i}/{total} ({len(chunk)} chars)...")

        workflow = copy.deepcopy(base_workflow)

        # Inject script text
        for node in workflow["nodes"]:
            if str(node["id"]) == NODE_TTS:
                node["widgets_values"][1] = chunk
                break

        # Inject voice reference file
        for node in workflow["nodes"]:
            if str(node["id"]) == NODE_LOADAUDIO:
                node["widgets_values"][0] = voice_file
                break

        # Set output filename
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
    _free_comfyui_memory()
    return AUDIO_FILE