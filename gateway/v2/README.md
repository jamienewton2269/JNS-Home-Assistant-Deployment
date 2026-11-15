# Gateway v2 — isolated validation prototype

This directory is **not connected** to the production trusted executor or Node C runner. It is a minimal fail-closed schema prototype for future compatibility testing.

Run locally: `cd gateway/v2 && python3 -m unittest -v`.

Only three keys are accepted: schema_version, job_id, job_type. The listed job types are *proposals*, not existing executor permissions. The validator does not authorize execution, target access, or output publication.

Next: inspect the actual Node C executor and queue contract; integrate only after regression testing and an explicit approved rollout. Keep raw logs off public Git.
