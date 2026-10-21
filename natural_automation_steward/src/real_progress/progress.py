"""Real Progress - framework-independent measured progress helper."""

from __future__ import annotations
import json
import os
import time
from pathlib import Path
from threading import Lock


__version__ = "1.0.2"
CONTRACT_VERSION = "1.0"


class ProgressModel:
    """Learned, stage-based progress with explicit running/stall/error states."""

    MODEL = "measured_stage_progress_with_learned_durations"

    def __init__(
        self,
        stats_path: str | Path,
        defaults: dict[str, float] | None = None,
        window: int = 20,
        stall_multiplier: float = 3.0,
        stall_min_seconds: float = 5.0,
    ):
        self.path = Path(stats_path)
        self.defaults = defaults or {}
        self.window = max(1, int(window))
        self.stall_multiplier = max(1.0, float(stall_multiplier))
        self.stall_min_seconds = max(0.1, float(stall_min_seconds))
        self.lock = Lock()

    def _load(self):
        with self.lock:
            if not self.path.exists():
                return {}
            try:
                return json.loads(self.path.read_text())
            except Exception:
                return {}

    def _save(self, data):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
            os.replace(tmp, self.path)

    def expected(self, name, stats=None):
        stats = stats if stats is not None else self._load()
        fallback = float(self.defaults.get(name, 0.1))
        return max(0.02, float((stats.get(name) or {}).get("avg", fallback)))

    def learn(self, stages):
        stats = self._load()
        changed = False
        for s in stages:
            if "duration" not in s:
                continue
            name = s.get("name")
            if not name:
                continue
            dur = max(0.0, float(s.get("duration") or 0))
            old = stats.get(name, {"count": 0, "avg": dur})
            count = int(old.get("count", 0))
            avg = float(old.get("avg", dur))
            n = min(count + 1, self.window)
            weighted_count = min(count, self.window - 1)
            new_avg = dur if count == 0 else ((avg * weighted_count) + dur) / n
            stats[name] = {"count": n, "avg": round(new_avg, 3)}
            changed = True
        if changed:
            self._save(stats)

    def _stall_info(self, active, active_elapsed, expected):
        if not active:
            return False, None, None
        expected_active = expected.get(active, self.expected(active))
        threshold = max(self.stall_min_seconds, expected_active * self.stall_multiplier)
        stalled = active_elapsed > threshold
        reason = None
        if stalled:
            reason = (
                f'Stage "{active}" has run for {active_elapsed:.1f}s; '
                f'learned expectation is {expected_active:.1f}s and stall threshold is {threshold:.1f}s.'
            )
        return stalled, threshold, reason

    def view(self, job, now=None):
        now = float(now if now is not None else time.time())
        stats = self._load()
        planned = list(job.get("planned_stages") or [])
        expected = {name: self.expected(name, stats) for name in planned}
        total_expected = sum(expected.values()) or 1.0

        elapsed = (job.get("ended") or now) - job["started"]
        stages = json.loads(json.dumps(job.get("stages") or []))
        if stages and "ended" not in stages[-1]:
            stages[-1]["duration"] = max(0.0, now - stages[-1]["started"])

        status = job.get("status", "running")
        active = job.get("stage")
        active_elapsed = 0.0
        completed_weight = 0.0
        active_fraction = 0.0

        for s in stages:
            name = s.get("name")
            if "ended" in s:
                completed_weight += expected.get(name, self.expected(name, stats))
            elif name == active:
                active_elapsed = float(s.get("duration") or 0)
                active_fraction = min(
                    0.97,
                    active_elapsed / max(expected.get(name, 0.1), 0.02),
                )

        stalled = False
        stall_threshold = None
        stall_reason = None

        if status == "done":
            percent, eta, state = 100.0, 0.0, "done"
        elif status == "error":
            # Do not count the failed active stage as completed work, even if
            # its process has ended. Preserve only genuinely completed stages
            # that occurred before the failing stage.
            error_completed_weight = 0.0
            for s in stages:
                name = s.get("name")
                if name == active:
                    continue
                if "ended" in s:
                    error_completed_weight += expected.get(name, self.expected(name, stats))
            percent = min(99.0, 100.0 * error_completed_weight / total_expected)
            eta, state = None, "error"
        else:
            active_weight = expected.get(active, 0.0) * active_fraction
            percent = max(
                0.0,
                min(99.0, 100.0 * (completed_weight + active_weight) / total_expected),
            )
            try:
                idx = planned.index(active)
            except ValueError:
                idx = -1
            if idx >= 0:
                eta = max(0.0, expected.get(active, 0.0) - active_elapsed)
                eta += sum(expected.get(x, 0.0) for x in planned[idx + 1 :])
            else:
                eta = sum(expected.values())

            stalled, stall_threshold, stall_reason = self._stall_info(
                active, active_elapsed, expected
            )
            if stalled:
                state = "stalled"
                eta = None
            elif active in (None, "", "Queued"):
                state = "queued"
            else:
                state = "running"

        return {
            **job,
            "stages": stages,
            "elapsed": round(elapsed, 3),
            "progress": {
                "percent": round(percent, 1),
                "eta_seconds": None if eta is None else round(eta, 2),
                "expected_total_seconds": round(total_expected, 2),
                "model": self.MODEL,
                "contract_version": CONTRACT_VERSION,
                "state": state,
                "stalled": stalled,
                "stall_threshold_seconds": (
                    None if stall_threshold is None else round(stall_threshold, 2)
                ),
                "stall_reason": stall_reason,
                "samples": {
                    k: int((stats.get(k) or {}).get("count", 0)) for k in planned
                },
            },
        }

