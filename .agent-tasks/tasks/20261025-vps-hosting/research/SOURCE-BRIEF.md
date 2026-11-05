# Source brief and requirement coverage

Created October 25, 2026 for task creation. Architectural authority remains `docs/hosting/vps/astra-plan.md`; rationale is `docs/hosting/vps/astra-analysis.md`. This brief indexes those sources without copying a second competing plan. The task files embed executable scope; the orchestrator coordinates work.

## Detected existing stack

- Backend: Python 3.13 runtime image, Django >=5.2, DRF, SimpleJWT, cryptography/Fernet, django-storages GCS, psycopg; requirements/pip workflow, pytest/pytest-django (`backend/pytest.ini`). Resolve the actual local environment before running commands; no Poetry/uv project manifest was found.
- Frontend: Node 24 build image, pnpm 11.13.1 lockfile, Vue 3.5, TypeScript 5.6, Vite 6, Pinia, Vitest 2. No frontend redesign is needed.
- Deployment: Bash, Docker/Compose v2, PostgreSQL 17-bookworm, host Caddy on Ubuntu 24.04. Existing script builds locally, backs up filesystem media and uses a deployment lock; target cloud operations are not implemented.
- Selected additions: private GHCR immutable artifacts, age public-key encryption, host journald/systemd, private GCS live/recovery buckets, pinned Authelia staging gateway. Select supported versions during implementation and record them.

## Coverage map

| Governing plan sections | Tasks / manual layer |
|---|---|
| 1–3 architecture, inventory, gates | 004, 012, orchestrator M0–M3 |
| 4.1 immutable environment/releases | 004–005, 010 |
| 4.2 correctness/draining/recovery | 001–003, 006 |
| 4.3 shared operations interface | 004, 006–011 |
| 5 host/secrets/provisioning | 012, M0/M1/M2 |
| 6 GCS/IAM/privacy | 007, 012, 015 |
| 7 proxy and staging authentication | 006, 012–013, 015 |
| 8 backups/manifests/restores/retention | 007–008, 010, 014–015 |
| 9 logging/schedules/monitoring | 009–011, 015 |
| 10 release and existing-data migration | 005–006, 016–017 |
| 11–12 recovery and failure exercises | 008, 014–017 |
| 13–15 operations/cost/commissioning | 010–012, 017, M3 |

Do not expand this effort into PITR, automatic failover, public media/CDN delivery, email features or recovery-media garbage collection. Those are outside the selected launch scope. Existing data import is conditional and explicitly owned by 016, not silently dropped.

## Sequencing clarifications

- The five coding phases produce locally verified software before real-provider evaluation. This refines the source plan's interleaved implementation/provisioning phases; it does not remove staging or recovery prerequisites.
- Code-task completion distinguishes local evidence from real GCS/systemd evidence. Tasks 015/017 own the latter; mocks never satisfy those tasks.
- Task 006 cannot permit valued-data deployment before task 007 wires in verified off-server backup. Bootstrap is limited to proven-empty synthetic environments.
- Log bundling must not require the offline age private key on the host: use encrypted chunk envelopes/indexes or another documented public-key-only arrangement, and prove decryption/reassembly during restore tests.
- Reboot reconciliation must control restart ordering, not just run a script after Docker has already restarted incompatible app code.
