# Watchtower execution plan

Baseline: 2026-10-17. This is a gated implementation plan, not a completion report.
No calendar estimate is committed before hosting, budget, operator, and integrations are selected.
Owner: project owner approves scope/cost/releases. Engineering implements. A separate reviewer
checks safety-sensitive changes. Independent security review is required before consequential use.

## Phase 0 - Establish an honest baseline
Tasks:
1. Preserve current branch heads and inventory committed files.
2. Review all locally drafted files as candidates; do not call them uploaded or deployed.
3. Approve documentation and source commits separately; do not overwrite the profile README.
4. Define protected assets, authorized identities, threat model, data sources, retention and budget.
5. Select assessment-only first, followed by blocking only one harmless lab tool.
Deliverables: architecture, implementation inventory, threat model and decision log.
Exit gate: owner signs off on scope, exclusions, evidence labels and test environment.

## Phase 1 - Repository hygiene and reproducible tests
Tasks:
1. Consolidate/review the seven-file gateway draft and four-file model-adapter draft.
2. Inspect dependencies, pin audited versions, add a lockfile and secret scanning.
3. Add ignore rules for credentials, databases, logs, screenshots and temporary artifacts.
4. Add CI for syntax, unit tests, integration tests and static checks; do not expose secrets to
   untrusted pull requests. Require review for control/permission/evaluation changes.
5. Use a development branch and reviewed pull request. Verify the file contents after commit.
Deliverables: reproducible source and CI output linked to exact commits.
Exit gate: one combined suite passes for the reviewed source; previous separate test counts
are not added together and presented as a single end-to-end result.

## Phase 2 - Working intake, evidence and visible dashboard
Tasks:
1. Add authenticated event intake, bounded schemas, per-caller limits and explicit source labels.
2. Persist event IDs, timestamps, processing states and failures before displaying outcomes.
3. Add authorized pagination/event streaming and a private dashboard using actual stored records.
4. Provide explicit buttons for synthetic test events; automatic sample feeds stay clearly labeled.
5. Connect one owner-authorized application log source; record its provenance limitations.
6. Implement redaction, retention, access logs, disk/capacity limits and backup/restore tests.
Acceptance tests: wrong credentials denied; invalid/oversized input rejected; an event survives
restart; dashboard matches stored records; collector failure is visible; no invented metrics.
Exit gate: operator can watch a real ingestion/storage cycle without any model configured.

## Phase 3 - Real text and image/text model assessment
Tasks:
1. Configure model identifiers, compatible API features and secrets on an authorized staging host.
2. Connect the adapter to validated HTTP routes and reviewed scenario retrieval.
3. Bound input/output sizes, inference concurrency, queue depth, timeouts, per-caller use and spend.
4. Decode/re-encode allowed images, reject unsupported/multi-frame inputs, and avoid arbitrary URL
   downloads. Do not claim this guarantees redaction or removes prompt injection.
5. Record model/configuration versions and separate unavailable/refused/truncated responses.
Acceptance tests: one real synthetic text call and one real non-sensitive image call; actual
provider failures never become success; costs and timing recorded without logging credentials.
Exit gate: live inference is independently observable, with owner-approved budget. Mocked tests
remain labeled mocked. No claim that the model's risk label is a safety guarantee.

## Phase 4 - Policy-mediated dummy execution
Tasks:
1. Register exactly one bounded dummy tool and derive identity from authentication.
2. Deny unknown tools/resources/arguments before invoking the analyst or executor.
3. Bind approvals and idempotency keys to exact identity/action/arguments/resource and policy.
4. Recheck authorization and stop state immediately before execution; fence stale queued jobs.
5. Record effect and receipt atomically where possible. Represent external timeouts as unknown
   until reconciled; never blindly retry a potentially completed consequential operation.
Acceptance tests: allowed dummy effect occurs once; unauthorized effect never occurs; changed
payload cannot reuse approval/key; duplicate/concurrent requests do not duplicate effects;
uncertain/unavailable required analysis denies execution; restart preserves decisions/state.
Exit gate: demonstrate protection at the receiving dummy resource, not just in the dashboard.

## Phase 5 - External operator control and host/network isolation
Tasks:
1. Separate operator and runtime identities/permissions and protect durable control state.
2. Verify gateway/agent cannot change control files, credentials, deployment, or audit authority.
3. Implement admission stop, supported cancellation, verification and scoped authorized resume.
4. Test stop during analysis, queued work, active work, restart and control-service failure.
5. Add externally controlled process supervision/network restrictions for the selected host.
Acceptance tests: verified loss of write access under the actual runtime identity; no new mediated
effects after admission-stop acknowledgment; active-work outcome reported truthfully; control
failure denies execution; only an authorized operator resumes; evidence survives restart.
Exit gate: publish measured stop semantics/latency and limitations. No global kill-switch claim.

## Phase 6 - Isolated decoy integration
Tasks:
1. Implement synthetic resources in a separate restricted lab environment.
2. Block production access independently; choose immediate denial or controlled decoy engagement.
3. Return synthetic results only to decoy sessions while keeping defender evidence truthful.
4. Restrict egress, resource consumption, execution capabilities and retention.
5. Send evidence to a service outside decoy write access. Persist authenticated session restrictions.
Acceptance tests: protected dummy resource unchanged; no production routes/credentials in decoy;
no unauthorized outbound destination reached; independent evidence matches response IDs;
engagement cannot remove logs or restrictions; reset removes decoy state but preserves evidence.
Exit gate: one authorized end-to-end test. The test does not prove the attacker believed success
or that all AI-origin activity is detectable. No public high-risk deployment yet.

## Phase 7 - Sandbox-boundary monitoring and behavioral evaluation
Tasks:
1. Inventory authorized agent workloads and available tool/host/network telemetry.
2. Capture benign baselines and reviewed suspicious cases, with consent and minimization.
3. Correlate observable signals; distinguish denied attempts from successful boundary crossings.
4. Build held-out tests independent of scenario generation and rule tuning.
5. Evaluate missed detections, false alarms, abstention, legitimate task completion, prevention,
   intervention latency, source coverage, availability and cost, with denominators/uncertainty.
6. Commission independent isolation/security review before connecting real consequential tools.
Exit gate: bounded claims backed by test records for a specified version and environment.

## Phase 8 - Governed learning and candidate improvements
Tasks:
1. Create authenticated review/labeling and provenance workflows; reviewer fields alone are not auth.
2. Keep observed, test-demonstrated and hypothetical scenarios distinct.
3. Let AI propose bounded prompt/retrieval/detection changes, not deploy them.
4. Evaluate candidates on protected held-out cases and safety regressions under fixed budgets.
5. Require independent approval, versioning, staged rollout, monitoring and rollback.
6. Consider fine-tuning only if evidence justifies it and data rights/privacy permit it.
Exit gate: a reviewer can reproduce a measured improvement without weakened controls.
This is governed improvement, not evidence of open-ended recursive self-improvement.

## Phase 9 - Restricted hosting pilot and release
Tasks:
1. Recheck the hosting connector; if unavailable, use an owner-authorized manual staging process.
2. Present service identity, access settings, region, persistence, secrets configuration and cost
   before creating services. No spending is authorized by this document.
3. Build/test deployment images and configuration; add HTTPS, authentication, rate limits,
   health/readiness checks, monitoring, backup/restore and incident-response procedures.
4. Start private and assessment-only with synthetic data, then one consented source.
5. Enable only explicitly reviewed low-impact tools after prior gates and operator drills pass.
6. Record deployment URL, commit/image identity, live checks, owner acceptance and rollback plan.
Exit gate: independently verified running service and dashboard, not merely a successful commit.

## Stop-work and rollback criteria
Stop promotion on a permission bypass, evidence tampering, unexplained production effect,
missing operator control, unapproved data disclosure, ambiguous effectful retry, or budget breach.
Pause new effectful work, revoke only authorized scoped access, preserve evidence, notify the
operator, and restore the last approved version after reviewing the incident. Do not hide failures
behind synthetic results. Record residual risks and decide whether the pilot may resume.

## First demonstration that counts
An authorized lab client requests a forbidden synthetic resource. The real path is denied;
optional decoy interaction returns a synthetic response. External evidence records the truth.
An operator stops further mediated actions. Independently inspect the receiving resource and
logs. Show these records in the dashboard with exact version, source labels, and limitations.
