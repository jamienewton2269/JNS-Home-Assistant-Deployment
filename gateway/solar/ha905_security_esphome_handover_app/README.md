# VM906 → VM905 native ESPHome guarded handover (inert source)

This app is **not a live security controller**. Never start on VM905 unless
the Node C guarded procedure first verifies all of the following:

- VM905 is healthy, six security automations remain disabled and Core config
  check passed; source VM906's one ESPHome entry still owns the device.
- Existing VM905 backup verified; source VM906 can be restored.
- Node A's automatic 45-minute VM906 recovery timer is active.
- VM906 has been **stopped** after the timer was armed and has been
  independently checked stopped. No duplicate security device controllers.
- The encrypted staged source record is copied privately, with verified
  source/target identity, to a short-lived file on the HAOS share data mount.
  The app only sees /share as read-only.
- The user understands that security inputs/outputs may be unavailable during
  the exclusive owner transfer and has a working manual backup and onsite
  confirmation plan.

The one-shot flow uses official POST /api/config/config_entries/flow and the
corresponding flow resource, handling user/encryption_key/authenticate steps.
No key or host is logged; no manual .storage edits are performed. A separate
Node C orchestrator must verify the final entry and physical functions and
then uninstall the app, erase the temporary share file and either mark
handover complete or restore VM906 on error.

Do not set permanent completion marker based on this app's "create_entry"
response alone; physical inputs, doorbell/tamper and output behaviour must be
verified with onsite operator. **Never disable the recovery timer on a
partially verified target**.
