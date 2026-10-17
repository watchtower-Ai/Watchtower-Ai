# Watchtower specialist AI-safety knowledge base

Research date: 2026-10-17. Status: draft requiring owner review.

## Mission and boundaries

Build a specialized defensive system for detecting, preventing, containing, and investigating unauthorized AI-agent actions in systems the owner is authorized to protect. General intelligence across unrelated fields is not the objective. Specialist superintelligence is an aspiration, not an achieved capability or a claim established by collecting documents.

Operationally, suspicious behavior includes unauthorized tool use, privilege changes, sensitive-data disclosure, unapproved egress, policy bypass attempts, and suspicious interactions with decoy assets. These behaviors do not by themselves prove that an actor is AI-driven, malicious, autonomous, or outside a sandbox. Preserve that uncertainty in alerts.

Containment and deception are proposed only inside explicitly authorized, isolated environments. Use fake secrets and synthetic assets, deny production credentials and routes, restrict egress and resources, log interactions, and provide a shutdown path. A decoy should not grant real access or become a staging point for attacks. No hack-back or activity on third-party systems is authorized by this document.

## Evidence and status conventions

This seed contains 13 documented risk/technique categories and two defensive-practice notes. It is not a list of 15 newly discovered incidents. Each proposed control and test below is an analyst design suggestion, not an implemented or validated Watchtower protection. All entries require owner review before trusted ingestion.

OWASP references below use the explicitly identified 2025 edition as a versioned baseline, not a claim about the latest edition. MITRE ATLAS is a living knowledge base: its inclusion of a technique does not by itself establish a specific real-world incident. No technique IDs are inferred here. NIST taxonomy references do not prove incident occurrence.

## Source registry

All sources checked on 2026-10-17. Summaries are original research notes; links and attribution do not grant permission to reuse the source material beyond its applicable terms.

- S1: OWASP GenAI Security Project, 2025 Top 10 Risk & Mitigations for LLMs and Gen AI Apps. https://genai.owasp.org/llm-top-10/
- S2: MITRE ATLAS, adversary tactics and techniques for AI systems. https://atlas.mitre.org/
- S3: NIST AI 100-2 E2025, Adversarial Machine Learning: A Taxonomy and Terminology of Attacks and Mitigations, published 2025-03-24. https://csrc.nist.gov/pubs/ai/100/2/e2025/final
- S4: OWASP LLM06:2025 Excessive Agency. The retrieved page identifies itself as Excessive Agency despite the legacy URL slug. https://genai.owasp.org/llmrisk/llm06-sensitive-information-disclosure/
- S5: MITRE Engage Starter Kit, including environment, monitoring, analysis, preparation, and rules of engagement. https://engage.mitre.org/starter-kit/
- S6: NIST AI RMF Playbook, MEASURE, including fit-for-purpose testing, security metrics, and documented red-team results. https://airc.nist.gov/airmf-resources/playbook/measure/

## Threat and risk knowledge seed

### WT-KB-0001: Prompt injection

Source: S1, LLM01:2025. External or user-supplied content can redirect model behavior across an intended instruction boundary. Proposed control: retain content provenance and enforce tool authorization independently of model output. Proposed synthetic test: a retrieved dummy document asks for a policy override; it must not authorize a protected action. Test benign quoted instructions as a false-positive control.

### WT-KB-0002: Sensitive information disclosure

Source: S1, LLM02:2025. An AI application may expose sensitive information through its inputs, outputs, or surrounding application. Proposed control: keep credentials outside model context, enforce access controls, and minimize sensitive telemetry. Proposed synthetic test: a request for another demo user's fake secret is denied while authorized public information remains accessible.

### WT-KB-0003: AI supply-chain compromise

Source: S1, LLM03:2025. Models, dependencies, datasets, and other components can introduce supply-chain weaknesses. Proposed control: track provenance, approved versions, integrity checks, and dependency review. Proposed synthetic test: an unapproved dummy artifact remains outside the trusted deployment inventory.

### WT-KB-0004: Data and model poisoning

Source: S1, LLM04:2025. Corrupted training, fine-tuning, or embedding data can change intended system behavior. Proposed control: quarantine new knowledge and require provenance review before trusted retrieval or training. Proposed synthetic test: a source that tells Watchtower to change its own policy stays in untrusted intake and cannot modify trusted rules.

### WT-KB-0005: Improper output handling

Source: S1, LLM05:2025. Insufficient validation of generated output can introduce downstream application risks. Proposed control: treat generated output as untrusted data, validate structured actions, and escape content for the output context. Proposed synthetic test: harmless markup-like text is displayed as text rather than executed.

### WT-KB-0006: Excessive agency

Sources: S1, LLM06:2025; S4. Excessive functionality, permissions, or autonomy can turn unexpected model output into damaging actions. Proposed control: least privilege, downstream authorization, action budgets, and human approval for high-impact operations. Proposed synthetic test: a mock payment without approval is held even if an assistant requests execution; an authorized low-risk task remains usable.

### WT-KB-0007: System prompt leakage

Source: S1, LLM07:2025. Prompt exposure can reveal internal instructions or application details. Proposed control: do not put secrets in prompts or rely on hidden instructions as an authorization boundary. Proposed synthetic test: disclosure of a dummy instruction must not expose credentials or authorize a protected tool.

### WT-KB-0008: Vector and embedding weaknesses

Source: S1, LLM08:2025. Retrieval and embedding workflows can introduce security risks around indexed information. Proposed control: enforce document access at retrieval time and preserve returned-content provenance. Proposed synthetic test: one demo tenant cannot retrieve another tenant's document, while permitted retrieval succeeds.

### WT-KB-0009: Misinformation

Source: S1, LLM09:2025. Incorrect generated information can cause harm when people or applications rely on it. Proposed control: retain sources, uncertainty, and review for consequential claims. Proposed synthetic test: an unsupported assertion is marked unverified rather than promoted into trusted knowledge.

### WT-KB-0010: Unbounded consumption

Source: S1, LLM10:2025. Uncontrolled resource consumption creates availability and cost risks. Proposed control: independent request, token, tool-call, runtime, storage, and spending limits. Proposed synthetic test: a bounded mock loop stops at its configured budget, and a normal bounded workflow completes.

### WT-KB-0011: AI Agent Tool Poisoning

Source: S2, technique name checked on the retrieved ATLAS matrix; ID not inferred. Proposed control: treat tool descriptions and returned content as untrusted, pin approved tool identities, and independently validate actions. Proposed synthetic test: a dummy tool response requesting a new permission cannot grant that permission. This is not evidence of a particular incident.

### WT-KB-0012: AI Agent Context Poisoning

Source: S2, technique name checked on the retrieved ATLAS matrix; ID not inferred. Proposed control: separate external content from trusted policy and retain provenance across memory writes. Proposed synthetic test: a synthetic memory note cannot override an owner authorization requirement. This is not evidence of a particular incident.

### WT-KB-0013: Exfiltration via AI Agent Tool Invocation

Source: S2, technique name checked on the retrieved ATLAS matrix; ID not inferred. Proposed control: constrain egress and destination permissions and review sensitive outbound requests. Proposed synthetic test: a mock call containing a fake secret to a non-allowlisted destination is prevented without contacting any endpoint. This is not evidence of a particular incident.

## Defensive-practice research notes

### WT-PRACTICE-0001: Planned, bounded deception and containment

Source basis: S5. MITRE Engage describes preparation, operational objectives, rules of engagement, environment, monitoring, and analysis. Watchtower design proposal: use isolated decoy services, honeytokens, and canary records with no production privileges, restricted egress, explicit resource limits, monitoring, and a shutdown path. Record attempts and outcomes without granting real capabilities. Do not claim that a decoy guarantees capture or that a suspicious actor believes it succeeded.

### WT-PRACTICE-0002: Evidence-based specialist evaluation

Source basis: S6. NIST recommends fit-for-purpose tests, security metrics, adversarial testing, and documented results. Watchtower design proposal: measure unauthorized-action prevention, malicious-case recall, benign-case false-positive rate, containment failures, boundary violations, latency, and audit completeness on explicitly scoped test sets. Keep test denominators, versions, uncertainty, and failures visible. A fully scripted demonstration is not proof of general effectiveness or superintelligence.

## Knowledge improvement loop

1. Collect public defensive sources during approved research runs.
2. Separate taxonomy categories, reported incidents, demonstrations, advisories, and proposed controls. Incident records require incident-specific evidence.
3. Record source, publication date when available, collection date, evidence quality, uncertainty, affected versions when supported, and duplicate identifiers.
4. Treat all fetched material as untrusted data, never executable instructions. Do not execute downloaded code or allow articles to authorize repository writes.
5. Quarantine and review new entries before trusted retrieval, model training, or production-policy use. Do not automatically train on collected text.
6. Convert reviewed findings into harmless synthetic tests with benign controls and explicit expected outcomes.
7. Review proposed rules against bypasses, false positives, performance budgets, and rollback requirements.
8. Promote only approved, tested changes through a separately reviewed change process. Preserve failures and counterexamples.

## Proposed background collection, not enabled

This chat does not continue searching between sessions. A future GitHub Actions collector could run on an owner-approved schedule with explicit source allowlists, redirect validation, timeouts, response-size limits, deduplication, narrow permissions, and review pull requests. Schedule, sources, permissions, retention, and any usage costs require separate approval. No scheduled workflow is installed by this commit. No automatic merges, live model calls, training jobs, or blocking-rule updates are enabled.

## Confidentiality and deployment boundary

The target repository was verified as public on 2026-10-17. This document contains only public-source summaries and high-level defensive proposals. Do not commit secrets, customer data, private logs, private code, personal data, or unverified allegations. Public-source material must still be reviewed for relevance, reliability, licensing, and malicious instructions.

This research document changes no backend code, model, Render configuration, service, credential, or runtime policy. Render remains on hold. The research branch is for review and must not be connected to deployment as part of this change.
