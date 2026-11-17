# Project recovery through the existing Node C gateway

Status: inventory and staged recovery plan; not proof of runner repair.

## Verified GitHub inventory (15 November 2026)
- HA: populated; assess its current runner usage
- JNS-Home-Assistant-Deployment: populated, public; contains legacy gateway queue and SAGE request/result transport
- ChatGPT_PSM: populated
- JNS-Steward-Diagnostics: populated, private
- adaptive-intelligence: populated
- Racecam: populated
- -BSC-Club-Manager: empty, private
- JNS-WESTMINSTER-CHIMES-: empty, private

Empty repositories do **not** mean source is lost: inspect authorised Node C/SAGE working copies before importing. Do not copy confidential files into public repos.

## Repair order
1. Identify current Node C self-hosted runner service, identity, registration, and workflow names without exposing secrets.
2. Inventory existing trusted executor handlers and queue schema. Existing `gateway_capabilities` request returned exit 64 (not allow-listed); do not retry unsupported operations.
3. Verify Node C-to-SAGE PowerShell transport using a read-only, allow-listed operation; keep command output private.
4. Run isolated gateway v2 tests; integrate validation/diagnostics with existing executor only after compatibility checks.
5. Implement authenticated per-project job profiles, idempotent queue, bounded batching, timeouts, structured error codes, safe retries and private artifact storage. No arbitrary shell from untrusted PRs.
6. Run read-only per-project preflight: workspace exists, clean/dirty Git state, build tools, dependencies, connectivity and safe deployment target.
7. Restore projects in separate PRs, each with its own tests and explicit release gate.

## Project recovery tracker
| Project | Repo | Recovery preflight | Deployment |
| --- | --- | --- | --- |
| HA deployment / gateway | JNS-Home-Assistant-Deployment | Executor/runner inventory needed | Not approved |
| Home Assistant | HA | Workspace, active HA target and rollback checks needed | Not approved |
| Adaptive Intelligence | adaptive-intelligence | Dashboard/integration regression needed | Not approved |
| Racecam / Android camera / receiver | Racecam | Compare SAGE/Node C sources with repo, Android and receiver build checks | Not approved |
| Club Manager V3 | -BSC-Club-Manager | Empty repo; verify CT101 source and independent V3 database before import | Not approved |
| Westminster Android/Alexa | JNS-WESTMINSTER-CHIMES- | Empty repo; inspect SAGE working copy and separate Alexa deployment | Not approved |
| Steward Diagnostics | JNS-Steward-Diagnostics | Private repository; read-only diagnostics review | Not approved |
| ChatGPT PSM | ChatGPT_PSM | Check whether it depends on gateway and build/test state | Not approved |

Additional projects that are not yet in these GitHub repositories must be discovered from authorised workspaces; do not assume they are already versioned.

## Security stop conditions
- Do not commit tokens, keys, full inventory, private command output, user data or sensitive configuration to public GitHub.
- Do not grant unrestricted PowerShell/SSH execution through PR-supplied job payloads.
- Do not change live Home Assistant, DHCP, club live site, Alexa production skill or other services until a tested rollback and explicit release authorisation are in place.
