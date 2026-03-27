# ============================================================
#  COMFYUI PROCESS MANAGER
#  Handles starting, stopping, and health-checking the
#  ComfyUI server process. Imported by batch.py and server.py.
# ============================================================

import time
import subprocess
import requests
import sys
from config import COMFYUI_URL, COMFYUI_PATH, COMFYUI_RESTART_EVERY

_process = None  # module-level handle to the ComfyUI subprocess


# ------------------------------------------------------------
#  Internal helpers
# ------------------------------------------------------------

def _is_ready() -> bool:
    """Return True if ComfyUI is responding to HTTP requests."""
    try:
        r = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _wait_until_ready(timeout: int = 120) -> bool:
    """
    Poll until ComfyUI is ready or timeout is reached.
    Returns True if ready, False if timed out.
    """
    print("   ⏳ Waiting for ComfyUI to be ready...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        if _is_ready():
            elapsed = int(time.time() - start)
            print(f" ready ({elapsed}s)")
            return True
        time.sleep(3)
        print(".", end="", flush=True)
    print(" TIMED OUT")
    return False


# ------------------------------------------------------------
#  Public API
# ------------------------------------------------------------

def start() -> bool:
    """
    Start ComfyUI as a background subprocess.
    If it's already running (externally or from a previous start()),
    this is a no-op.
    Returns True if ComfyUI is ready, False on failure.
    """
    global _process

    # Already running externally — nothing to do
    if _is_ready():
        print("✅ ComfyUI already running")
        return True

    print(f"🚀 Starting ComfyUI...")
    print(f"   Path : {COMFYUI_PATH}")

    _process = subprocess.Popen(
        [sys.executable, COMFYUI_PATH, "--listen"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP  # Windows: clean kill
    )

    return _wait_until_ready()


def stop():
    """
    Stop the ComfyUI process if we started it.
    Does nothing if ComfyUI was started externally.
    """
    global _process

    if _process is None:
        return

    print("🛑 Stopping ComfyUI...")
    try:
        _process.terminate()
        _process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        _process.kill()
        _process.wait()
    except Exception:
        pass

    _process = None
    print("   ComfyUI stopped")


def restart() -> bool:
    """
    Stop and restart ComfyUI. Used between batch video runs
    to guarantee a clean VRAM state.
    Returns True if ComfyUI came back up successfully.
    """
    print("\n🔄 Restarting ComfyUI for clean VRAM state...")
    stop()
    time.sleep(3)  # brief pause to let the port release
    return start()


def is_running() -> bool:
    """Return True if ComfyUI is currently responding."""
    return _is_ready()