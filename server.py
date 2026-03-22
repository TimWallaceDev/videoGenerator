# ============================================================
#  SERVER — FastAPI backend
#  Provides a web UI for submitting topics and monitoring
#  pipeline progress over Tailscale.
#
#  Install: pip install fastapi uvicorn python-multipart
#  Run:     python server.py
#  Access:  http://[your-tailscale-ip]:8000
# ============================================================

import os
import sys
import json
import uuid
import threading
import traceback
from datetime import datetime
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Add videoGenerator to path
sys.path.insert(0, os.path.dirname(__file__))

from main   import run_pipeline
from status import pipeline_status
from config import OUTPUT_DIR, BASE_DIR

app = FastAPI(title="Video Pipeline")

# Static files (frontend)
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

# ============================================================
#  Queue management
# ============================================================

class QueueItem:
    def __init__(self, topic: str):
        self.id         = str(uuid.uuid4())[:8]
        self.topic      = topic
        self.status     = "queued"   # queued | running | done | failed
        self.added_at   = datetime.now().isoformat()
        self.output     = None
        self.error      = None

    def to_dict(self):
        return {
            "id":       self.id,
            "topic":    self.topic,
            "status":   self.status,
            "added_at": self.added_at,
            "output":   self.output,
            "error":    self.error,
        }


queue        = deque()        # pending items
history      = []             # completed/failed items
queue_lock   = threading.Lock()
worker_thread = None


def queue_worker():
    """Background thread that processes queue items one at a time."""
    while True:
        item = None
        with queue_lock:
            if queue:
                item = queue.popleft()

        if item is None:
            threading.Event().wait(2)  # sleep 2s then check again
            continue

        item.status = "running"
        pipeline_status.start(item.topic)

        try:
            output_path = run_pipeline(topic=item.topic, auto=True)
            item.status = "done"
            item.output = output_path
            pipeline_status.finish(output_path)

        except Exception as e:
            item.status = "failed"
            item.error  = str(e)
            pipeline_status.fail(str(e))
            traceback.print_exc()

        with queue_lock:
            history.insert(0, item)  # newest first
            # Keep last 50 in history
            while len(history) > 50:
                history.pop()


def start_worker():
    global worker_thread
    if worker_thread is None or not worker_thread.is_alive():
        worker_thread = threading.Thread(target=queue_worker, daemon=True)
        worker_thread.start()


# ============================================================
#  API routes
# ============================================================

class TopicRequest(BaseModel):
    topic: str


@app.on_event("startup")
def startup():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    start_worker()
    print(f"\n🌐 Server running — share this with your friend on Tailscale:")
    print(f"   http://[your-tailscale-ip]:8000\n")


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    """Serve the frontend HTML."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>Frontend not found. Add static/index.html</h1>")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.post("/queue")
def add_to_queue(req: TopicRequest):
    """Add a topic to the processing queue."""
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    item = QueueItem(topic)
    with queue_lock:
        queue.append(item)

    return {"id": item.id, "topic": topic, "position": len(queue)}


@app.get("/queue")
def get_queue():
    """Get current queue and history."""
    with queue_lock:
        return {
            "queue":   [item.to_dict() for item in queue],
            "history": [item.to_dict() for item in history],
        }


@app.delete("/queue/{item_id}")
def remove_from_queue(item_id: str):
    """Remove a queued item (only if not yet running)."""
    with queue_lock:
        for item in list(queue):
            if item.id == item_id:
                queue.remove(item)
                return {"removed": True}
    raise HTTPException(status_code=404, detail="Item not found or already running")


@app.get("/status")
def get_status():
    """Get current pipeline status."""
    return pipeline_status.to_dict()


@app.get("/videos")
def list_videos():
    """List all completed videos in the output folder."""
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
    """Download a completed video file."""
    # Security: only allow .mp4 files from output dir
    if not filename.endswith(".mp4") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(
        filepath,
        media_type="video/mp4",
        filename=filename
    )


# ============================================================
#  Entry point
# ============================================================

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",   # listen on all interfaces (required for Tailscale)
        port=8000,
        reload=False,
    )