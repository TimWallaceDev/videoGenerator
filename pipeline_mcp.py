"""
MCP server — Video Pipeline Bridge

Exposes the local video pipeline API (http://localhost:8000) as native
Claude tools so Cowork sessions can queue videos from inside the sandbox.

Run via Claude Desktop's MCP config:
  "command": "python", "args": ["C:/Users/RAZER/videoGenerator/pipeline_mcp.py"]
"""

import json
import requests
from mcp.server.fastmcp import FastMCP

PIPELINE_URL = "http://localhost:8000"

mcp = FastMCP("video-pipeline")


def _pipeline_available() -> bool:
    try:
        requests.get(f"{PIPELINE_URL}/queue", timeout=3)
        return True
    except requests.RequestException:
        return False


@mcp.tool()
def queue_video(
    topic: str,
    script: str,
    mode: str = "short",
    style: str = "serious",
    image_model_id: str = "sdxl_fast",
    music_id: str = "none",
) -> str:
    """
    Queue a video for production in the local pipeline.

    topic          : Title / topic label (used for the output filename).
    script         : Full narration script. Each sentence becomes one image frame.
                     Write 8-14 complete sentences for Shorts, more for long-form.
    mode           : "short" (vertical YouTube Shorts) or "long" (landscape video).
    style          : "serious" (authoritative tone) or "funny" (dry wit).
    image_model_id : Image generation model — "sdxl_fast" (default, fastest),
                     "qwen_image", "flux_dev", "z_image", "z_image_turbo".
    music_id       : Background music track ID, or "none". Call list_music() first
                     to see available tracks.
    """
    if not _pipeline_available():
        return "❌ Pipeline unavailable — is the server running at localhost:8000?"

    payload = {
        "topic":          topic,
        "script":         script,
        "mode":           mode,
        "style":          style,
        "image_model_id": image_model_id,
        "music_id":       music_id,
        "skip_research":  True,
    }

    try:
        res = requests.post(f"{PIPELINE_URL}/queue", json=payload, timeout=10)
        res.raise_for_status()
        data = res.json()
        return f"✅ Queued at position {data.get('position', '?')}: \"{topic}\" (id: {data.get('id', '?')})"
    except requests.HTTPError as e:
        return f"❌ Pipeline rejected the request: {e}"
    except requests.RequestException as e:
        return f"❌ Could not reach pipeline: {e}"


@mcp.tool()
def get_queue() -> str:
    """
    Return the current video pipeline queue and recent history.
    Shows pending videos, what's currently running, and recently completed or failed jobs.
    """
    if not _pipeline_available():
        return "❌ Pipeline unavailable — is the server running at localhost:8000?"

    try:
        res = requests.get(f"{PIPELINE_URL}/queue", timeout=10)
        res.raise_for_status()
        data = res.json()

        queue   = data.get("queue",   [])
        history = data.get("history", [])

        lines = []

        pending = [i for i in queue if i.get("status") != "running"]
        running = [i for i in queue if i.get("status") == "running"]

        if running:
            r = running[0]
            lines.append(f"🎬 RUNNING: \"{r['topic']}\" [{r.get('mode','?')} / {r.get('style','?')}]")

        if pending:
            lines.append(f"\n⏳ QUEUED ({len(pending)}):")
            for i, item in enumerate(pending, 1):
                lines.append(f"  {i}. \"{item['topic']}\" [{item.get('mode','?')} / {item.get('style','?')}]")
        else:
            lines.append("\n⏳ Queue is empty.")

        if history:
            lines.append(f"\n📋 RECENT ({min(len(history), 5)}):")
            for item in history[:5]:
                status = item.get("status", "?")
                icon   = "✅" if status == "done" else "❌" if status == "failed" else "—"
                lines.append(f"  {icon} \"{item['topic']}\" — {status}")

        return "\n".join(lines)

    except requests.RequestException as e:
        return f"❌ Could not reach pipeline: {e}"


@mcp.tool()
def list_music() -> str:
    """
    List available background music tracks for videos.
    Returns track IDs and labels. Pass the ID to queue_video() as music_id.
    Use "none" for no music.
    """
    if not _pipeline_available():
        return "❌ Pipeline unavailable — is the server running at localhost:8000?"

    try:
        res = requests.get(f"{PIPELINE_URL}/music", timeout=10)
        res.raise_for_status()
        data    = res.json()
        tracks  = data.get("tracks", [])
        default = data.get("default", "none")

        if not tracks:
            return "No music tracks available. Use music_id=\"none\" for silence."

        lines = ["Available music tracks:\n"]
        for t in tracks:
            marker = " ← default" if t["id"] == default else ""
            lines.append(f"  {t['id']:20s}  {t['label']}{marker}")

        return "\n".join(lines)

    except requests.RequestException as e:
        return f"❌ Could not reach pipeline: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
