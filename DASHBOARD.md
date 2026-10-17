# Blue-eye Watchtower dashboard: private staging build

Status: locally tested candidate, not a deployed service. This package does not implement
AI-agent blocking, honeypot deployment, an external stop control, RSI, image-analysis routes,
or automatic collection from external systems. Those remain separate workstreams.

## Local run
Place these files in the root of the Watchtower repository, alongside its existing backend.py.
Python 3.10+ is required. Run:
python watchtower_web.py
Open the localhost address printed in the terminal. Paste the generated DASHBOARD token into
its Connect field. It is not an OpenAI key. Stop the server with Ctrl+C.
The standalone HTML preview is visual only; it cannot collect or display API data without a server.

The app stores actual submitted events in a separate SQLite database outside the repository.
Select Add 5 synthetic records to see labeled records enter storage and appear in the event list.
This does not call a model. Submitted records are not proof of malicious AI activity or training.
The database is unencrypted local storage with file permissions, not an external tamper-proof log.
Use synthetic, non-sensitive input only. There is no automatic secret redaction or deletion UI.

## Optional real text analysis
Before starting the server, configure OPENAI_API_KEY and OPENAI_MODEL through secure runtime
settings. Never paste the provider key into the dashboard, chat, logs, or GitHub. Select a model
compatible with the existing backend's Chat Completions JSON-mode request.
A model request occurs only when an authenticated event explicitly sets analyze=true (the UI
checkbox). Submitted tool names/arguments leave your machine and can incur provider charges.
Set provider spending limits. The app defaults to 20 requested analyses per UTC day, persisted
in SQLite, adjustable with WATCHTOWER_DAILY_ANALYSIS_LIMIT (0-100). This is a request-count
limit, not a monetary guarantee. Duplicate matching idempotency keys do not request analysis again.
AI provider failures appear as unavailable; absent model configuration is not_configured.
The displayed configured flag does not prove a successful live inference.

## Tests and verification
python -m unittest -v test_watchtower_web.py
Fifteen local tests passed, including real localhost HTTP storage, authentication, duplicate
handling, persistence, request budgeting, input validation and mocked provider failure/success.
JavaScript syntax was checked with Node. A browser-rendering/interaction test, a real provider
call, hosting deployment, dependency audit and public-service security review were not performed.
These tests are separate from earlier registry/gateway/model tests and are not a combined suite.

## Hosting preparation, not deployment
requirements-dashboard.txt supplies Gunicorn for a Linux staging host; audit and lock dependencies
before use. The local wsgiref server is development-only and binds to loopback.
A hosted command can use the factory watchtower_web:create_app() under Gunicorn, but requires
WATCHTOWER_API_TOKEN (strong random ASCII, >=32 characters) and WATCHTOWER_DASHBOARD_DB on a
persistent protected volume. Do not choose a paid service or expose it publicly without approval.
Add private-network/access restrictions, HTTPS, request/header timeouts, rate limits, backups,
retention, monitoring and a security review before a hosted pilot. The UI shell and /healthz
are public if you expose the service; event data requires the shared token. There is no multi-user
identity or role separation yet. Only one private operator should use this prototype.
The current CSP permits inline application scripts/styles; additional hardening is needed.
No external service is created by committing these files. Render connection must be rechecked.

## Included files
watchtower_web.py: WSGI API and local launch command; imports existing backend.py only for inference.
web/index.html: responsive blue-eye interface with real API polling and truthful capability labels.
test_watchtower_web.py: 15 local tests, with provider responses explicitly mocked.
requirements-dashboard.txt: staging server dependency, not a production lockfile.
DASHBOARD.md: these instructions and limitations.
