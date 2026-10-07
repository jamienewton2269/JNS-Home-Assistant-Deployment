# JNS Node C Gateway Queue

The gateway uses immutable FIFO-style job submissions instead of a single mutable request/result pair.

## Submit a job

Create a new executable shell payload under:

`gateway/queue/YYYYMMDDTHHMMSSZ-short-description-uniqueid.sh`

Lexicographic filename order is execution order. Use UTC timestamps plus a unique suffix to avoid collisions.

The Node C self-hosted GitHub runner serializes gateway workflows and the dispatcher always scans queued jobs oldest-first.

## Results

Each job gets independent files:

- `gateway/results/<job-id>.txt` — complete stdout/stderr and exit code
- `gateway/status/<job-id>.json` — running/done/failed/timeout metadata
- `gateway/index.tsv` — compact index of all known job states

Completed jobs are never re-run while their result and status files exist.

## Safety

Each job is capped by `JNS_GATEWAY_JOB_TIMEOUT` (default 900 seconds). A timeout or failed job records its own failure and does not erase or overwrite another job.

## Legacy compatibility

`gateway/request.sh` is retained. When a future commit changes that file, the workflow copies that exact revision into a uniquely named queue job based on the triggering commit SHA, then dispatches it. Existing tools can therefore continue using `request.sh` while new work should submit directly to `gateway/queue/`.
