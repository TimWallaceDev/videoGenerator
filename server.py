# ============================================================
#  SERVER — FastAPI backend
#  Queue is persisted to disk and survives server restarts.
# ============================================================

import os
import sys
import json
import uuid
import threading
import traceback
from datetime import datetime
from collections import deque

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))

from main   import run_pipeline
from status import pipeline_status
from config import OUTPUT_DIR, BASE_DIR, VOICES, DEFAULT_VOICE_ID, CAPTIONS_DEFAULT
import comfyui

app = FastAPI(title="Video Pipeline")

STATIC_DIR = os.path.join(BASE_DIR, "static")
QUEUE_FILE = os.path.join(BASE_DIR, "queue_state.json")
os.makedirs(STATIC_DIR, exist_ok=True)


# ============================================================
#  Queue item
# ============================================================

class QueueItem:
    def __init__(
        self,
        topic:       str,
        mode:        str  = "long",
        style:       str  = "serious",
        voice_id:    str  = None,
        captions:    bool = None,
        style_notes: str  = "",
        item_id:     str  = None,
        added_at:    str  = None,
        status:      str  = "queued",
        output:      str  = None,
        error:       str  = None,
    ):
        self.id          = item_id or str(uuid.uuid4())[:8]
        self.topic       = topic
        self.mode        = mode
        self.style       = style
        self.voice_id    = voice_id    or DEFAULT_VOICE_ID
        self.captions    = captions    if captions is not None else CAPTIONS_DEFAULT
        self.style_notes = style_notes or ""
        self.status      = status
        self.added_at    = added_at or datetime.now().isoformat()
        self.output      = output
        self.error       = error

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "topic":       self.topic,
            "mode":        self.mode,
            "style":       self.style,
            "voice_id":    self.voice_id,
            "captions":    self.captions,
            "style_notes": self.style_notes,
            "status":      self.status,
            "added_at":    self.added_at,
            "output":      self.output,
            "error":       self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QueueItem":
        return cls(
            topic       = d["topic"],
            mode        = d.get("mode",        "long"),
            style       = d.get("style",       "serious"),
            voice_id    = d.get("voice_id",    DEFAULT_VOICE_ID),
            captions    = d.get("captions",    CAPTIONS_DEFAULT),
            style_notes = d.get("style_notes", ""),
            item_id     = d.get("id"),
            added_at    = d.get("added_at"),
            status      = d.get("status",      "queued"),
            output      = d.get("output"),
            error       = d.get("error"),
        )


# ============================================================
#  Persistence
# ============================================================

queue      = deque()
history    = []
queue_lock = threading.Lock()


def _save_queue():
    data = {
        "queue":   [item.to_dict() for item in queue],
        "history": [item.to_dict() for item in history],
    }
    tmp = QUEUE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, QUEUE_FILE)


def _load_queue():
    if not os.path.exists(QUEUE_FILE):
        return
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        print("⚠️  Could not load queue_state.json — starting fresh")
        return

    for d in data.get("queue", []):
        item = QueueItem.from_dict(d)
        if item.status == "running":
            item.status = "queued"
            item.error  = None
            print(f"   ↩️  Reset interrupted job: {item.topic}")
        queue.append(item)

    for d in data.get("history", []):
        history.append(QueueItem.from_dict(d))

    print(f"   📂 Loaded {len(queue)} queued, {len(history)} history items")


# ============================================================
#  Worker
# ============================================================

worker_thread = None


def queue_worker():
    while True:
        item = None
        with queue_lock:
            if queue:
                item = queue[0]

        if item is None:
            threading.Event().wait(2)
            continue

        if not comfyui.is_running():
            pipeline_status.log("⚠️  ComfyUI not responding — restarting...")
            if not comfyui.restart():
                item.status = "failed"
                item.error  = "ComfyUI failed to restart"
                with queue_lock:
                    queue.popleft()
                    history.insert(0, item)
                    _save_queue()
                continue

        item.status = "running"
        with queue_lock:
            _save_queue()

        pipeline_status.start(item.topic)

        try:
            output_path = run_pipeline(
                topic=item.topic,
                auto=True,
                mode=item.mode,
                style=item.style,
                voice_id=item.voice_id,
                captions=item.captions,
                style_notes=item.style_notes,
            )
            item.status = "done"
            item.output = output_path
            pipeline_status.finish(output_path)

        except Exception as e:
            item.status = "failed"
            item.error  = str(e)
            pipeline_status.fail(str(e))
            traceback.print_exc()

        with queue_lock:
            queue.popleft()
            history.insert(0, item)
            while len(history) > 50:
                history.pop()
            _save_queue()


def start_worker():
    global worker_thread
    if worker_thread is None or not worker_thread.is_alive():
        worker_thread = threading.Thread(target=queue_worker, daemon=True)
        worker_thread.start()


# ============================================================
#  API routes
# ============================================================

class TopicRequest(BaseModel):
    topic:       str
    mode:        str  = "long"
    style:       str  = "serious"
    voice_id:    str  = DEFAULT_VOICE_ID
    captions:    bool = CAPTIONS_DEFAULT
    style_notes: str  = ""


@app.on_event("startup")
def startup():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with queue_lock:
        _load_queue()

    if comfyui.is_running():
        print("✅ ComfyUI already running")
    else:
        print("🚀 Starting ComfyUI...")
        if not comfyui.start():
            print("⚠️  ComfyUI failed to start")

    start_worker()
    print(f"\n🌐 Server running on http://0.0.0.0:8000\n")


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>Frontend not found. Add static/index.html</h1>")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/voices")
def list_voices():
    """Return available voices for the frontend dropdown."""
    return {"voices": VOICES, "default": DEFAULT_VOICE_ID}


@app.post("/queue")
def add_to_queue(req: TopicRequest):
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    mode  = req.mode  if req.mode  in ("long", "short")           else "long"
    style = req.style if req.style in ("serious", "funny") else "serious"

    # Validate voice_id
    valid_ids = {v["id"] for v in VOICES}
    voice_id  = req.voice_id if req.voice_id in valid_ids else DEFAULT_VOICE_ID

    item = QueueItem(
        topic=topic, mode=mode, style=style,
        voice_id=voice_id, captions=req.captions,
        style_notes=req.style_notes,
    )
    with queue_lock:
        queue.append(item)
        _save_queue()

    return {"id": item.id, "topic": topic, "position": len(queue)}


@app.get("/queue")
def get_queue():
    with queue_lock:
        return {
            "queue":   [item.to_dict() for item in queue],
            "history": [item.to_dict() for item in history],
        }


@app.delete("/queue/{item_id}")
def remove_from_queue(item_id: str):
    with queue_lock:
        for item in list(queue):
            if item.id == item_id:
                if item.status == "running":
                    raise HTTPException(status_code=400, detail="Cannot remove a running job")
                queue.remove(item)
                _save_queue()
                return {"removed": True}
    raise HTTPException(status_code=404, detail="Item not found")


@app.get("/status")
def get_status():
    return pipeline_status.to_dict()


@app.get("/comfyui/status")
def comfyui_status():
    return {"running": comfyui.is_running()}


@app.post("/comfyui/restart")
def comfyui_restart():
    return {"success": comfyui.restart()}


@app.get("/videos")
def list_videos():
    if not os.path.exists(OUTPUT_DIR):
        return {"videos": []}
    videos = []
    for f in sorted(os.listdir(OUTPUT_DIR), reverse=True):
        if f.endswith(".mp4"):
            path     = os.path.join(OUTPUT_DIR, f)
            size_mb  = os.path.getsize(path) / (1024 * 1024)
            modified = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
            videos.append({
                "filename": f,
                "size_mb":  round(size_mb, 1),
                "modified": modified,
                "url":      f"/download/{f}",
            })
    return {"videos": videos}


@app.get("/download/{filename}")
def download_video(filename: str):
    if not filename.endswith(".mp4") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(filepath, media_type="video/mp4", filename=filename)


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)