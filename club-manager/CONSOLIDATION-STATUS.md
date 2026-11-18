# BSC Club Manager — source consolidation register

Status: **source located; integration and installation NOT complete**. Updated 2026-11-18.

## Authoritative source candidates

1. **Advanced Club Manager beta**: this repository's `club-manager/` tree on `main`. CT101 recovery merge commit `eecb553c51899948d26b3823b5620341322ccb21` contains 50 recovered files, including `beta/server.py`, browser UI, commissioning gate, and synthetic finance, payments, YBM and committee components. The separate commit `553123e` is a gateway result receipt, **not** the beta source commit.
2. **Membership/Joomla bridge**: Node C local clean repository `/opt/bsc-joomla-membership`, branch `master`, commit `90fd97240b7045d946e32af04fe56357d465ef69`. Read-only inventory workflow run `44315512321` records 46 Python, 18 PHP, 1 SQL, no tracked HTML or JS. Contains signed snapshot, replica, member-change queue, Joomla plugin and isolated acceptance fixtures.
3. **Dedicated GitHub repository**: `jamienewton2269/-BSC-Club-Manager`; not yet confirmed to contain either full source tree. Do not deploy from it until source parity is established.
4. **CT101**: authoritative intended PostgreSQL/backend environment. The Node C inventory cannot inspect CT101 (`pct` unavailable), so database schema and running service parity remain **unverified**.

## Non-destructive integration rules

- Preserve both source trees and their full Git history. Do not overwrite or delete the beta, Node C source, or CT101 installation.
- One canonical repository should contain `club-manager/` for the Python/backend and beta interface and `joomla-bridge/` for the existing Node C bridge. Integrate via explicit APIs, not duplicated databases.
- Do not import production member data into GitHub, logs, test fixtures or development databases.
- No automatic deployment to Joomla V2/live, CT101, or Krystal V3.
- Before promotion: capture SHA256 manifests for both trees, compare overlapping APIs/schema/migrations, validate dependencies and complete synthetic tests including disposable MySQL, then perform a fresh isolated installation and officer acceptance.

## Verified acceptance evidence

- Node C source inventory: `gateway/receipts/bsc-reconciliation-inventory-latest.txt`, run `44315512321`.
- PHP isolated syntax 18/18, signed snapshot verifier and member intake passed in `gateway/receipts/bsc-php-lint-latest.txt`; disposable MySQL portal and importer tests outstanding.
- Node C Python: last published receipt `gateway/receipts/bsc-nodec-tests-latest.txt`, 132 passed / 12 skipped.
- CT101 production parity, integrated UI/API, and fresh installation: **not verified**.

## Immediate merge gate

Import the tracked Node C source into a review branch of the canonical repository without rewriting `club-manager/`. Compare and test both modules, then merge only after the review branch demonstrates complete source preservation. The existing source on Node C must remain unchanged.
