# ============================================================
#  STATUS MODULE — Shared pipeline status
#  All pipeline modules write progress here.
#  The API server reads it and serves it to the frontend.
# ============================================================

import time
from datetime import datetime


class PipelineStatus:
    """
    Singleton-style status object shared across all pipeline modules.
    Thread-safe enough for single-pipeline-at-a-time use.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.running       = False
        self.topic         = ""
        self.step          = ""
        self.step_num      = 0
        self.step_total    = 5
        self.detail        = ""
        self.progress      = 0    # 0-100
        self.started_at    = None
        self.finished_at   = None
        self.error         = None
        self.output_file   = None
        self.log_lines     = []

    def start(self, topic: str):
        self.reset()
        self.running    = True
        self.topic      = topic
        self.started_at = datetime.now().isoformat()
        self.log(f"Pipeline started: {topic}")

    def update(self, step: str, step_num: int, detail: str = "", progress: int = 0):
        self.step     = step
        self.step_num = step_num
        self.detail   = detail
        self.progress = progress
        self.log(f"[Step {step_num}/5] {step}: {detail}" if detail else f"[Step {step_num}/5] {step}")

    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.log_lines.append(line)
        # Keep last 200 lines
        if len(self.log_lines) > 200:
            self.log_lines = self.log_lines[-200:]
        # Also print to terminal
        print(line)

    def finish(self, output_file: str):
        self.running     = False
        self.finished_at = datetime.now().isoformat()
        self.output_file = output_file
        self.progress    = 100
        self.detail      = "Complete"
        self.log(f"Pipeline complete: {output_file}")

    def fail(self, error: str):
        self.running  = False
        self.error    = error
        self.detail   = f"Failed: {error}"
        self.log(f"Pipeline failed: {error}")

    def to_dict(self) -> dict:
        elapsed = None
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end   = datetime.fromisoformat(self.finished_at) if self.finished_at else datetime.now()
            elapsed = int((end - start).total_seconds())

        return {
            "running":     self.running,
            "topic":       self.topic,
            "step":        self.step,
            "step_num":    self.step_num,
            "step_total":  self.step_total,
            "detail":      self.detail,
            "progress":    self.progress,
            "started_at":  self.started_at,
            "finished_at": self.finished_at,
            "elapsed_sec": elapsed,
            "error":       self.error,
            "output_file": self.output_file,
            "log_lines":   self.log_lines[-50:],  # last 50 lines to frontend
        }


# Global singleton — imported by all pipeline modules
pipeline_status = PipelineStatus()