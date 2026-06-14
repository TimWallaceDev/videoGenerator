# ============================================================
#  IMAGEGEN MODULE — Multi-model image generation via ComfyUI
#
#  Each image model is a full ComfyUI API-format workflow stored
#  in workflows/, with an injection map in config.IMAGE_MODELS
#  telling this module where to plug in prompt, negative prompt,
#  resolution, and seed.
# ============================================================

import os
import json
import time
import copy
import uuid
import random
import requests
import websocket
from config import (
    COMFYUI_URL,
    WORKFLOWS_DIR,
    IMAGES_DIR,
    IMAGE_PROMPT_PREFIX,
    VIDEO_CONFIGS,
    IMAGE_MODELS,
    DEFAULT_IMAGE_MODEL_ID,
    get_image_model,
)
from status import pipeline_status

PROMPT_PREFIX = IMAGE_PROMPT_PREFIX


# ------------------------------------------------------------
#  Workflow loading + injection
# ------------------------------------------------------------

_workflow_cache: dict[str, dict] = {}


def _load_workflow_template(filename: str) -> dict:
    """Load and cache a workflow JSON from WORKFLOWS_DIR."""
    if filename not in _workflow_cache:
        path = os.path.join(WORKFLOWS_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            _workflow_cache[filename] = json.load(f)
    return _workflow_cache[filename]


def _build_api_workflow(
    prompt_text: str,
    model_id: str = None,
    seed: int = None,
    mode: str = "long",
) -> dict:
    """
    Build a ready-to-submit ComfyUI API workflow for the given image model.

    - Loads the workflow template (cached after first load)
    - Deep-copies it (templates are mutable dicts, never share state)
    - Injects the positive prompt (with IMAGE_PROMPT_PREFIX)
    - Injects the negative prompt, if the model supports one
    - Sets resolution to match VIDEO_CONFIGS[mode]
    - Sets a random seed if none provided
    """
    spec = get_image_model(model_id or DEFAULT_IMAGE_MODEL_ID)

    template = _load_workflow_template(spec["workflow"])
    wf = copy.deepcopy(template)

    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    full_prompt = PROMPT_PREFIX + prompt_text

    # --- Positive prompt ---
    wf[spec["prompt_node"]]["inputs"]["text"] = full_prompt

    # --- Negative prompt (only if this model has one) ---
    if spec["negative_node"]:
        wf[spec["negative_node"]]["inputs"]["text"] = ""

    # --- Resolution ---
    cfg = VIDEO_CONFIGS[mode]
    wf[spec["latent_node"]]["inputs"]["width"]  = cfg["width"]
    wf[spec["latent_node"]]["inputs"]["height"] = cfg["height"]

    for node_id, w_key, h_key in spec.get("extra_size_nodes", []):
        wf[node_id]["inputs"][w_key] = cfg["width"]
        wf[node_id]["inputs"][h_key] = cfg["height"]

    # --- Seed ---
    wf[spec["seed_node"]]["inputs"][spec["seed_key"]] = seed

    return wf


# ------------------------------------------------------------
#  ComfyUI queue / wait / download helpers
#  (model-agnostic — unchanged regardless of which image model runs)
# ------------------------------------------------------------

def _queue_prompt(api_workflow: dict) -> tuple[str, str]:
    client_id = str(uuid.uuid4())
    payload = {
        "prompt":     api_workflow,
        "client_id":  client_id,
        "extra_data": {"extra_pnginfo": {}},
    }
    response = requests.post(f"{COMFYUI_URL}/prompt", json=payload)
    response.raise_for_status()
    return response.json()["prompt_id"], client_id


def _free_comfyui_memory():
    """Tell ComfyUI to fully unload image models from VRAM."""
    try:
        requests.post(f"{COMFYUI_URL}/free", json={
            "unload_models": True,
            "free_memory":   True,
        }, timeout=10)
        print("   🧹 ComfyUI image models unloaded from VRAM")
    except requests.RequestException:
        pass


def _wait_for_completion(prompt_id: str, client_id: str, timeout: int = 600):
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
            history = response.json()
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                if outputs:
                    return
        except requests.RequestException:
            pass
        time.sleep(3)


def _get_output_image(prompt_id: str) -> tuple[str, str]:
    for _ in range(10):
        response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
        history = response.json()

        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            for node_id, node_output in outputs.items():
                if "images" in node_output:
                    img_info = node_output["images"][0]
                    return img_info["filename"], img_info.get("subfolder", "")

        time.sleep(1)

    raise RuntimeError(f"Could not find image output for prompt {prompt_id}")


def _download_image(filename: str, subfolder: str, dest_path: str):
    params = {"filename": filename, "type": "output"}
    if subfolder:
        params["subfolder"] = subfolder

    response = requests.get(f"{COMFYUI_URL}/view", params=params)
    response.raise_for_status()

    with open(dest_path, "wb") as f:
        f.write(response.content)


# ------------------------------------------------------------
#  Main function
# ------------------------------------------------------------

def generate_images(
    prompts: list[str],
    mode: str = "long",
    model_id: str = None,
) -> list[str]:
    """
    Generate one image per prompt string using the selected image model.

    model_id : ID from config.IMAGE_MODELS. Defaults to DEFAULT_IMAGE_MODEL_ID.
    Returns an ordered list of local image file paths.
    """
    os.makedirs(IMAGES_DIR, exist_ok=True)

    spec  = get_image_model(model_id or DEFAULT_IMAGE_MODEL_ID)
    total = len(prompts)
    img_paths = []

    print(f"🖼️  Generating {total} images [{spec['label']}]...")

    for i, prompt in enumerate(prompts, 1):
        pct = 60 + int((i / total) * 25)
        pipeline_status.update("Image Generation", 5, f"Image {i}/{total} [{spec['label']}]", pct)
        print(f"   Image {i}/{total}...")

        api_workflow = _build_api_workflow(prompt, model_id=model_id, mode=mode)
        prompt_id, client_id = _queue_prompt(api_workflow)
        _wait_for_completion(prompt_id, client_id)

        filename, subfolder = _get_output_image(prompt_id)
        dest = os.path.join(IMAGES_DIR, f"img_{i:04d}.png")
        _download_image(filename, subfolder, dest)
        img_paths.append(dest)

        print(f"   ✅ Image {i} saved")

    _free_comfyui_memory()
    print(f"✅ All {total} images generated")
    return img_paths
