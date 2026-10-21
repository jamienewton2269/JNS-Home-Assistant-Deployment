import tempfile
from pathlib import Path
from progress import ProgressModel

def run():
    with tempfile.TemporaryDirectory() as d:
        m=ProgressModel(Path(d)/"stats.json",defaults={"A":2.0,"B":4.0},stall_multiplier=3.0,stall_min_seconds=5.0)
        job={"id":"t","status":"running","started":100.0,"stage":"B","planned_stages":["A","B"],
             "stages":[{"name":"A","started":100.0,"ended":102.0,"duration":2.0},{"name":"B","started":102.0}]}
        live=m.view(job,now=103.0)
        assert live["progress"]["state"]=="running"
        assert live["progress"]["percent"]==50.0
        assert live["progress"]["eta_seconds"]==3.0
        stalled=m.view(job,now=115.0)
        assert stalled["progress"]["state"]=="stalled"
        assert stalled["progress"]["eta_seconds"] is None
        assert stalled["progress"]["stall_threshold_seconds"]==12.0
        done=m.view({**job,"status":"done","ended":106.0},now=120.0)
        assert done["progress"]["percent"]==100.0
        error=m.view({**job,"status":"error","ended":103.0},now=120.0)
        assert error["progress"]["state"]=="error"
        m.learn([{"name":"A","duration":3.0},{"name":"B","duration":6.0}])
        assert m._load()["A"]["count"]==1
    print("PASS: running, learned ETA, stall, done, error, persistence")

if __name__=="__main__":
    run()
