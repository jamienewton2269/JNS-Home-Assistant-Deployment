#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${1:-gateway}"
QUEUE="$ROOT/queue"
RESULTS="$ROOT/results"
STATUS="$ROOT/status"
INDEX="$ROOT/index.tsv"
TIMEOUT_SECONDS="${JNS_GATEWAY_JOB_TIMEOUT:-900}"
EXECUTOR="/usr/local/sbin/jns-gateway-exec"

mkdir -p "$QUEUE" "$RESULTS" "$STATUS"

json_status() {
  local file="$1" job="$2" state="$3" started="$4" finished="$5" rc="$6"
  python3 - "$file" "$job" "$state" "$started" "$finished" "$rc" <<'PY'
import json,sys
path,job,state,started,finished,rc=sys.argv[1:]
obj={"job_id":job,"state":state,"started":started or None,"finished":finished or None,
     "exit_code":None if rc=="" else int(rc)}
with open(path,"w",encoding="utf-8") as f:
    json.dump(obj,f,indent=2,sort_keys=True)
    f.write("\n")
PY
}

rebuild_index() {
  python3 - "$STATUS" "$INDEX" <<'PY'
import glob,json,os,sys
status_dir,index=sys.argv[1:]
rows=[]
for p in sorted(glob.glob(os.path.join(status_dir,"*.json"))):
    try:
        d=json.load(open(p,encoding="utf-8"))
    except Exception:
        continue
    rows.append((d.get("job_id",""),d.get("state",""),d.get("exit_code"),
                 d.get("started") or "",d.get("finished") or ""))
with open(index,"w",encoding="utf-8") as f:
    f.write("job_id\tstate\texit_code\tstarted\tfinished\n")
    for r in rows:
        f.write("\t".join("" if x is None else str(x) for x in r)+"\n")
PY
}

[[ -x "$EXECUTOR" ]] || {
  echo "Trusted executor missing: $EXECUTOR" >&2
  exit 78
}

processed=0
while IFS= read -r jobfile; do
  base="$(basename "$jobfile" .json)"
  result="$RESULTS/$base.txt"
  status="$STATUS/$base.json"

  if [[ -f "$result" && -f "$status" ]]; then
    continue
  fi

  started="$(date -Is)"
  json_status "$status" "$base" "running" "$started" "" ""
  rebuild_index

  tmp="$result.tmp"
  set +e
  {
    echo "=== JNS NODE C TRUSTED GATEWAY JOB ==="
    echo "job_id=$base"
    echo "started=$started"
    echo "runner=$(hostname)"
    echo
    timeout --signal=TERM --kill-after=15s "$TIMEOUT_SECONDS" \
      sudo "$EXECUTOR" "$jobfile"
  } >"$tmp" 2>&1
  rc=$?
  set -e

  finished="$(date -Is)"
  {
    echo
    echo "finished=$finished"
    echo "exit_code=$rc"
  } >>"$tmp"
  mv "$tmp" "$result"

  if [[ "$rc" -eq 0 ]]; then state="done";
  elif [[ "$rc" -eq 124 || "$rc" -eq 137 ]]; then state="timeout";
  else state="failed"; fi

  json_status "$status" "$base" "$state" "$started" "$finished" "$rc"
  rebuild_index
  processed=$((processed+1))
done < <(find "$QUEUE" -maxdepth 1 -type f -name '*.json' -print | LC_ALL=C sort)

rebuild_index
echo "gateway_json_jobs_processed=$processed"
