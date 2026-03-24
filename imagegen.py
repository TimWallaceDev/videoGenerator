# ============================================================
#  IMAGEGEN MODULE — Qwen Image via ComfyUI
#  Generates one image per sentence prompt, saves to IMAGES_DIR.
#  Uses the expanded subgraph nodes directly (ComfyUI API
#  does not support subgraph node types natively).
# ============================================================

import os
import json
import time
import uuid
import random
import requests
import websocket
from config import (
    COMFYUI_URL,
    IMAGEGEN_WORKFLOW,
    IMAGES_DIR,
    TEMP_DIR,
    IMAGE_PROMPT_PREFIX,
    VIDEO_CONFIGS,
)
from status import pipeline_status

# Use prefix from config
PROMPT_PREFIX = IMAGE_PROMPT_PREFIX


# ------------------------------------------------------------
#  Build the API workflow from expanded subgraph nodes
# ------------------------------------------------------------

def _build_api_workflow(prompt_text: str, seed: int = None, mode: str = "long") -> dict:
    """
    Build the ComfyUI API format workflow dict from the known
    Qwen image subgraph nodes. All node IDs and connections are
    hardcoded from the exported workflow JSON.
    """
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    full_prompt = PROMPT_PREFIX + prompt_text

    api_workflow = {
        # --- Load models ---
        "37": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "qwen_image_fp8_e4m3fn.safetensors",
                "weight_dtype": "default",
            }
        },
        "38": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "type": "qwen_image",
                "device": "default",
            }
        },
        "39": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "qwen_image_vae.safetensors",
            }
        },

        # --- LoRA ---
        "73": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["37", 0],
                "lora_name": "Qwen-Image-Lightning-4steps-V1.0.safetensors",
                "strength_model": 1.0,
            }
        },

        # --- Sampling shift ---
        "66": {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {
                "model": ["73", 0],
                "shift": 3.1,
            }
        },

        # --- Prompts ---
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["38", 0],
                "text": full_prompt,
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["38", 0],
                "text": "",  # negative prompt (empty)
            }
        },

        # --- Latent image (size depends on mode) ---
        "58": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width":      VIDEO_CONFIGS[mode]["width"],
                "height":     VIDEO_CONFIGS[mode]["height"],
                "batch_size": 1,
            }
        },

        # --- KSampler (4 steps, cfg 1.0, euler/simple) ---
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["66", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["58", 0],
                "seed": seed,
                "steps": 4,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            }
        },

        # --- Decode ---
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["39", 0],
            }
        },

        # --- Save ---
        "60": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": "pipeline/img",
            }
        },
    }

    return api_workflow


# ------------------------------------------------------------
#  ComfyUI queue / wait / download helpers
# ------------------------------------------------------------

def _queue_prompt(api_workflow: dict) -> tuple[str, str]:
    """Submit workflow to ComfyUI, return (prompt_id, client_id)."""
    client_id = str(uuid.uuid4())
    payload   = {
        "prompt":      api_workflow,
        "client_id":   client_id,
        "extra_data":  {"extra_pnginfo": {}},
    }
    response  = requests.post(f"{COMFYUI_URL}/prompt", json=payload)
    response.raise_for_status()
    return response.json()["prompt_id"], client_id


def _free_comfyui_memory():
    """
    Tell ComfyUI to fully unload image models from VRAM.
    Called once after all images are generated, before moving to next step.
    """
    try:
        requests.post(f"{COMFYUI_URL}/free", json={
            "unload_models": True,  # fully evict Qwen from VRAM
            "free_memory":   True,
        }, timeout=10)
        print("   🧹 ComfyUI image models unloaded from VRAM")
    except requests.RequestException:
        pass  # non-critical, continue regardless


def _wait_for_completion(prompt_id: str, client_id: str, timeout: int = 600):
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


def _get_output_image(prompt_id: str) -> tuple[str, str]:
    """
    Poll ComfyUI history to find the output image filename.
    Returns (filename, subfolder).
    """
    for _ in range(10):
        response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
        history  = response.json()

        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            for node_id, node_output in outputs.items():
                if "images" in node_output:
                    img_info = node_output["images"][0]
                    return img_info["filename"], img_info.get("subfolder", "")

        time.sleep(1)

    raise RuntimeError(f"Could not find image output for prompt {prompt_id}")


def _download_image(filename: str, subfolder: str, dest_path: str):
    """Download a generated image from ComfyUI."""
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

def generate_images(prompts: list[str], mode: str = "long") -> list[str]:
    """
    Generate one image per prompt string.
    Returns an ordered list of local image file paths.
    """
    os.makedirs(IMAGES_DIR, exist_ok=True)

    total     = len(prompts)
    img_paths = []

    print(f"🖼️  Generating {total} images...")

    for i, prompt in enumerate(prompts, 1):
        pct = 60 + int((i / total) * 25)
        pipeline_status.update("Image Generation", 5, f"Image {i}/{total}", pct)
        print(f"   Image {i}/{total}...")

        api_workflow = _build_api_workflow(prompt, mode=mode)
        prompt_id, client_id = _queue_prompt(api_workflow)
        _wait_for_completion(prompt_id, client_id)

        filename, subfolder = _get_output_image(prompt_id)
        dest = os.path.join(IMAGES_DIR, f"img_{i:04d}.png")
        _download_image(filename, subfolder, dest)
        img_paths.append(dest)

        print(f"   ✅ Image {i} saved")

    # All images done — now unload models to free VRAM for next step
    _free_comfyui_memory()
    print(f"✅ All {total} images generated")
    return img_paths


# ------------------------------------------------------------
#  Entry point for isolated testing
# ------------------------------------------------------------

if __name__ == "__main__":
    test_prompts = [
        "A quiet rural landscape in early nineteenth century North America, "
        "rolling farmland, wooden fences, overcast sky, documentary style",

        "A mid-century urban street in a North American city, brick buildings, "
        "period automobiles, pedestrians in 1950s clothing, afternoon light",
    ]

    print("🧪 Testing imagegen module...")
    paths = generate_images(test_prompts)

    print(f"\n✅ Imagegen test complete.")
    for p in paths:
        print(f"   {p}")