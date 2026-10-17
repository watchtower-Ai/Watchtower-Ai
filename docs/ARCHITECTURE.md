# Watchtower architecture

Design baseline: 2026-10-17. Status: proposed architecture, not a statement of deployed capability.
Scope: authorized environments and assets whose owners approve monitoring and response.

## 1. Mission and boundaries
Detect unauthorized or dangerous agent behavior, protect real resources, preserve evidence,
and support human-controlled response. Isolated deception supplements access controls;
production protection must not depend on fooling an attacker.

Autonomy is not evidence of malicious intent. Record observed behavior, policy violations,
AI attribution confidence, and confirmed effects separately. Do not claim global AI visibility,
universal containment, guaranteed intent detection, catastrophe prediction, or open-ended RSI.
No unauthorized scanning, hack-back, production credentials in decoys, or real infrastructure
control is part of the initial product. Start with one harmless lab resource.

## 2. Trust zones and data flow

Authorized agents / authorized telemetry / explicitly labeled synthetic events
    -> authenticated intake and bounded schema validation
    -> identity, resource scope, deterministic policy and stop-state checks
    -> optional AI assessment and human approval where required
    -> final authorization recheck and restricted execution adapter
    -> independently observed effect and protected evidence record

Suspicious requests -> deny real access first
                    -> optional isolated decoy engagement
                    -> synthetic response to the decoy client
                    -> truthful observation to the evidence service

Separate operator control -> admission stop / cancellation / containment verification / resume
Evidence service -> authenticated dashboard and review queue
Reviewed research -> scenario registry -> bounded retrieval context, not privileged instructions

Trust zones: caller, gateway, analyst, executor, decoy, evidence, operator, and build/evaluation.
Folders alone do not isolate these zones. Enforce identities, credentials, network routes,
read/write permissions, and deployment boundaries. Initial modules can share a repository;
operator and decoy privileges must not simply inherit the gateway's privileges.

## 3. Components and proposed implementation

| Component | Responsibility | Initial implementation direction |
| --- | --- | --- |
| Intake API | Authenticate, validate size/schema, rate-limit, identify source | Typed Python HTTP service |
| Policy engine | Deterministic allow/deny/review with versioned rules | Pure functions plus external authorization checks |
| Executor | Run allowlisted operations only, never arbitrary model code | One bounded dummy tool, then reviewed adapters |
| AI analyst | Text assessment and later image/text assessment | Configured hosted-model adapter; no execution credentials |
| Scenario registry | Provenance, review, uncertainty, benign counterexamples | Versioned records; draft records excluded from retrieval |
| Decoy service | Synthetic resources/responses, bounded interaction | Separate lab environment with no production route |
| Host/network sensors | Observe boundary crossings outside agent control | Approved platform telemetry; select after hosting is known |
| Evidence store | Requests, decisions, approvals, outcomes and correlated observations | PostgreSQL target; SQLite for bounded local prototype |
| Operator service | Stop admission, request cancellation, verify containment, authorize resume | Separate identity and protected durable state |
| Dashboard | Truthful live status, source labels, model errors and review | Authenticated event list/stream; no fabricated counters |
| Evaluation runner | Unit/integration/adversarial/held-out tests | Isolated fixtures plus deployment-like staging tests |
| Improvement workflow | Propose and evaluate changes, never self-authorize | Review queue, version comparison, human approval and rollback |

A distributed queue is not needed merely to claim high worker counts. Choose concurrency from
measured latency, resource use, bounded queue depth, and cost limits. Durable queues become a
separate milestone when workloads require them.

## 4. Deterministic enforcement and mathematical checks

An action is eligible only if all applicable conditions hold:
Authenticated AND WithinScope AND PolicyPermits AND RequiredApprovalValid AND NOT Stopped.
An AI assessment can trigger denial/review; it cannot override an explicit policy denial.
Passing this predicate proves only those conditions, not universal harmlessness.

Testable invariants:
- An agent cannot grant permissions, change operator controls, or promote its own policy.
- Every protected execution path is mediated; direct backend credentials are unavailable.
- Approval binds identity, exact action/arguments/resource, policy version, expiry and single use.
- Authorization and stop state are checked immediately before effectful execution.
- Duplicate requests cannot duplicate effects; changed payloads cannot reuse an approval/key.
- Required control failure denies consequential execution and creates an operational alert.
- Decoy networks/identities have no production route or usable production credentials.
- The authoritative evidence store is outside decoy/agent write access.
- Missing evidence means unknown, not safe or successfully blocked.

Use explicit state machines and bounded threat models; do not treat an LLM score as a formal
proof. Later formal verification must identify the exact properties and environment modeled.

## 5. Defensive deception protocol

Expose synthetic resources only inside an authorized decoy environment. Fake documents,
canary records and decoy credentials must not authenticate to real services. Avoid arbitrary
command execution, uncontrolled egress, unlimited sessions, and sensitive payload retention.

For each interaction record request ID, authenticated identity if available, source/session,
operation, resource, timestamps, observed response, response_is_synthetic, real_effect_status,
policy decision, containment action, and independent verification references.

Possible client response: apparent completion. Defender record: synthetic response only;
production effect not executed or unknown, as established by actual integration evidence.
A hardcoded production_operation_performed=false field is not proof of isolation.
Decoy contact does not prove AI involvement, intent, belief in the response, or permanent capture.
Session restrictions must use authenticated identities and persist across workers/restarts.
Choose between immediate denial and continued isolated engagement through explicit policy.

## 6. Sandbox monitoring and operator controls

Observe tool, host and network boundaries from outside the agent sandbox. Monitor permitted
platform signals such as denied resource access, unexpected processes/connections, decoy-token
use and attempts to modify protected controls. Attempts are not automatically successful escapes.
Containerization is not a universal sandbox-escape guarantee; choose stronger isolation where
required, then test it with authorized specialists.

Separate stop semantics:
- ADMISSION_STOPPED: no new mediated effectful work may begin.
- CANCEL_REQUESTED: cancellation sent; work may still be active.
- CONTAINMENT_VERIFIED: the relevant supervisor/tool confirms the documented outcome.
- RESUMED: authorized operator releases stop with explicit scope and audit evidence.

Persist stop state. Fence stale queued jobs and revalidate approvals after policy/control changes.
A local stop flag is not a global kill switch. Completed effects require separate recovery.
Revoke only scoped credentials and connections the operator is authorized to control.

## 7. AI, data, and governed improvement

Text and image/text adapters are separate from authorization. Initially accept bounded text
and vetted single-frame PNG/JPEG; audio/video are future scope. Treat retrieved text, image text,
and model outputs as untrusted. Validate outputs and record model/configuration versions.
Configure credentials through secret settings, provider spending controls and request budgets.
No automatic sensitive-data uploads; define source permissions, redaction, retention and deletion.

Keep raw permitted evidence separate from normalized analysis copies. Label sources as
synthetic, submitted, observed, or externally reported, with provenance limitations.
An HTTP collector or event archive does not itself train a model.

Improvement workflow: reviewed feedback -> candidate change -> isolated tests -> protected
held-out evaluation -> independent human approval -> restricted rollout -> monitoring/rollback.
The candidate cannot edit its graders, permissions, stop mechanism, or production deployment.
Fine-tuning is optional later; do not call prompt changes or scenario storage unrestricted RSI.

## 8. Design basis

Use NIST zero-trust principles for external policy enforcement and continuing authorization:
https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-207.pdf
Use CISA decoy guidance as a supplement to existing controls, not their replacement:
https://www.cisa.gov/resources-tools/resources/using-cyber-decoys-strengthen-detection-and-response
Use AISI's tool/host/network isolation distinction when designing evaluations:
https://www.aisi.gov.uk/blog/the-inspect-sandboxing-toolkit-scalable-and-secure-ai-agent-evaluations
Use measured evaluations before optimization/fine-tuning:
https://platform.openai.com/docs/guides/fine-tuning
These sources inform the design; they do not certify Watchtower.
