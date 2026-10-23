# Skill Demo

A working local demonstration of an **Enterprise AI Skills Lifecycle**: author → submit → scan → build → approve → publish → revoke.

## Run locally

Requires Python 3.10+. No third-party packages, API keys, or AI subscriptions needed.

```sh
git clone https://github.com/anmonu/skill-demo.git
cd skill-demo
python3 server.py
```

Open **http://127.0.0.1:8000**. The server binds to loopback only. Data persists in `.data/demo.sqlite3`. Stop with Ctrl+C. Use `python3 server.py --port 8001 --db .data/another-demo.sqlite3` for a separate demo.

## Five-minute walkthrough

1. As **Alex · Employee**, select **Create a skill → Load safe sample → Save draft**.
2. Select **Submit for checks → Run security checks → Build package**. Inspect **View evidence** for the report and SHA-256 digest.
3. Switch to **Sam · Security reviewer**. Select **Approve → Publish to catalog**.
4. Switch back to Alex. Open **Approved catalog** and download the ZIP containing `manifest.json` and `SKILL.md`.
5. Open **Audit trail** and export the event history.
6. Create another skill with **Load unsafe sample**. Submit and scan: findings block building and approval. Create a corrected version to continue.
7. For organisation distribution, create a safe skill with **Organisation** scope. Only **Jordan · Organisation admin** can approve and publish it. Every demo role can download it. Jordan can revoke it, removing it from the catalog and disabling future downloads.

The app does not install or execute skills in an AI runtime. Revocation cannot recall already downloaded files.

## Working features

- SQLite persistence for immutable versioned manifests, findings, artifacts, approvals, and event history.
- Server-enforced transitions; failed checks block packaging and out-of-order actions are rejected.
- Illustrative checks for credential patterns, unsafe shell instructions, prompt overrides, external URLs, and excess permissions.
- Reproducible ZIP packages; approvals and downloads verify SHA-256 integrity.
- Distinct author/reviewer/admin actors with scope-sensitive decisions and author-only individual downloads.
- GitHub Actions validates committed skill manifests, tests, scans and packages them, and uploads evidence and ZIPs.
- Responsive dashboard, evidence viewer, catalog, and audit export.

## Two demonstration paths

**Interactive:** dashboard → local API → SQLite. Identities are simulated with a role selector and `X-Demo-Role` header. These actions do **not** create GitHub commits or pull requests, trigger Actions, or change real organisation permissions. Scanning and builds run synchronously locally.

**Repository:** change `skills/<skill-name>/manifest.json` on a branch, commit, and open a pull request. GitHub Actions runs the actual validation/scan/package pipeline on the commit. Download evidence and packages from the workflow run. See `skills/meeting-summary/manifest.json`. CI does not approve or publish to the local catalog. GitHub PR reviews can demonstrate human decisions, but required reviewers and branch protections must be configured separately; this repository does not enforce merge approval.

Both paths share manifest validation, policy, and packaging in `lifecycle.py`. Webhook integration is a production-phase item.

## Verify

```sh
python3 -m unittest discover -s tests -v
python3 scripts/pipeline.py
```

Results: `build/scan-report.json` and `build/*.zip`. A failed scan exits nonzero. CI uploads packages only when all checks pass.

## Production phase

This demo is not a production identity or security boundary. Anyone with local access can choose a role. The scanner is a small heuristic deny-list that can miss unsafe instructions, not a substitute for SAST, secret scanning, dependency auditing, prompt evaluations, or human review. Local audit rows are mutable by the database owner. No submitted code is executed and no AI inference is performed.

Next phase:

- SSO/OIDC, employee identities, team membership, RBAC, independent reviewer policies.
- GitHub App, per-employee commits/PRs, verified webhooks, durable jobs, commit-to-artifact provenance.
- Maintainer-controlled scanning policy and protected CI configuration; contributors must not approve their own checks.
- Sandboxed scanners and evaluations with no untrusted execution in privileged runners.
- Protected branches and deployment environments, required security/business approvals, immutable evidence.
- Signed artifacts in a private registry, tenant-aware installation, version pinning, runtime revocation.
- Central append-only audit storage, secrets management, rate limits, retention and monitoring.

No GitHub token is requested or stored by the app. Keep this demo on localhost; do not expose it through a public tunnel or use it as a multi-user service.
