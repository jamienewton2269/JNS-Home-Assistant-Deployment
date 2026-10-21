"""Real Progress consumer adapter.

Small thread-safe job registry for projects that do not already have one.
Projects with an existing job registry can use ProgressModel directly.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from progress import ProgressModel


class JobTracker:
    def __init__(self, model: ProgressModel):
        self.model = model
        self.jobs = {}
        self.lock = threading.Lock()

    def start(self, planned_stages, metadata=None, job_id=None):
        now = time.time()
        jid = job_id or uuid.uuid4().hex
        job = {
            "id": jid,
            "status": "running",
            "started": now,
            "updated": now,
            "stage": "Queued",
            "planned_stages": list(planned_stages or []),
            "stages": [],
        }
        if metadata:
            job["metadata"] = dict(metadata)
        with self.lock:
            self.jobs[jid] = job
        return jid

    def stage(self, job_id, name):
        now = time.time()
        with self.lock:
            job = self.jobs[job_id]
            stages = job["stages"]
            if stages and "ended" not in stages[-1]:
                stages[-1]["ended"] = now
                stages[-1]["duration"] = round(now - stages[-1]["started"], 3)
            stages.append({"name": str(name), "started": now})
            job["stage"] = str(name)
            job["updated"] = now

    def finish(self, job_id, result=None):
        stages = self._close(job_id, "done", result=result)
        self.model.learn(stages)

    def fail(self, job_id, error):
        # Failed executions are observable but must not train normal-duration history.
        self._close(job_id, "error", error=str(error))

    def _close(self, job_id, status, result=None, error=None):
        now = time.time()
        with self.lock:
            job = self.jobs[job_id]
            if job["stages"] and "ended" not in job["stages"][-1]:
                s = job["stages"][-1]
                s["ended"] = now
                s["duration"] = round(now - s["started"], 3)
            job["updated"] = now
            job["ended"] = now
            job["status"] = status
            if result is not None:
                job["result"] = result
            if error is not None:
                job["error"] = error
            return json.loads(json.dumps(job["stages"]))

    def view(self, job_id):
        with self.lock:
            job = json.loads(json.dumps(self.jobs[job_id]))
        return self.model.view(job)

    def forget(self, job_id):
        with self.lock:
            return self.jobs.pop(job_id, None) is not None
