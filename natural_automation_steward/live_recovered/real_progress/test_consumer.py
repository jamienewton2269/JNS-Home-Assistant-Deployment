import tempfile
import time
from pathlib import Path

from consumer import JobTracker
from progress import ProgressModel


def run():
    with tempfile.TemporaryDirectory() as d:
        stats = Path(d) / "stats.json"
        model = ProgressModel(stats, defaults={"one": 0.05, "two": 0.05}, stall_min_seconds=0.2)
        jobs = JobTracker(model)

        jid = jobs.start(["one", "two"], {"consumer": "test"})
        queued = jobs.view(jid)
        assert queued["progress"]["state"] == "queued"
        jobs.stage(jid, "one")
        time.sleep(0.02)
        jobs.stage(jid, "two")
        mid = jobs.view(jid)
        assert mid["progress"]["state"] == "running"
        assert 0 < mid["progress"]["percent"] < 100
        jobs.finish(jid, {"ok": True})
        done = jobs.view(jid)
        assert done["status"] == "done"
        assert done["progress"]["percent"] == 100.0
        learned_after_success = stats.read_text()

        bad = jobs.start(["one"], job_id="failed-job")
        jobs.stage(bad, "one")
        time.sleep(0.01)
        jobs.fail(bad, "expected test failure")
        failed = jobs.view(bad)
        assert failed["status"] == "error"
        assert failed["progress"]["state"] == "error"
        assert stats.read_text() == learned_after_success

        assert jobs.forget("failed-job")
        print("PASS: consumer lifecycle, successful learning, failed-run isolation")


if __name__ == "__main__":
    run()
