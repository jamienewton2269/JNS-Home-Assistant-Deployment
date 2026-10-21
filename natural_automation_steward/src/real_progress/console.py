"""Dependency-free terminal renderer for Real Progress."""

from __future__ import annotations


def render_console(job, width=32):
    p = job.get("progress") or {}
    pct = max(0.0, min(100.0, float(p.get("percent") or 0.0)))
    width = max(10, int(width))
    filled = int(round(width * pct / 100.0))
    bar = "#" * filled + "-" * (width - filled)
    eta = p.get("eta_seconds")
    eta_text = "ETA ?" if eta is None else f"ETA {float(eta):.1f}s"
    state = str(p.get("state") or job.get("status") or "unknown").upper()
    stage = str(job.get("stage") or "Queued")
    elapsed = float(job.get("elapsed") or 0.0)
    return f"[{bar}] {pct:5.1f}%  {state:7}  {elapsed:5.1f}s  {eta_text:>9}  {stage}"
