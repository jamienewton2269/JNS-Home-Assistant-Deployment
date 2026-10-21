# v1.0.0 Consolidation Release

## Purpose

This release freezes feature expansion and consolidates the working Natural Automation + HA Steward prototype into a reproducible, testable source-controlled release.

## Included

- recovered live Node B baseline committed for provenance
- canonical GitHub source tree
- complete Real Progress source and tests
- server-side short-lived automation proposals
- user-facing Apply confirmation path
- transactional `automations.yaml` writer
- Home Assistant config validation
- restart/read-back verification and rollback
- migration-safe HA-General role resolver
- removal of fixed VM905 / fixed Node B assumptions
- DNS-first Proxmox peer configuration
- searchable Steward repair knowledge store
- deterministic seeding from existing HA repair/test scripts
- v1 installer with pre-release snapshot and rollback script
- CI release gate including rendered JavaScript syntax validation

## Historical repair corpus

The v1 CI seed currently discovers 17 existing Home Assistant repair/test procedures in the repository. They are imported as `manual_review`, non-portable advisory knowledge until locally validated.

## Deliberately deferred

No new autonomous repair capability is added in v1.

Repair execution, integration installation, pairing, service migration and unrestricted shell access remain outside the Natural Automation write scope.

## Source provenance

`live_recovered/` contains the source recovered from the active Node B installation on 2026-10-21 before consolidation.
