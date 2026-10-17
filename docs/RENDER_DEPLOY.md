# Deploy Watchtower from GitHub to Render

This is a staging Blueprint for the committed monitoring dashboard, not the full
AI-defense platform. Saving these files to GitHub does not create a Render service.
Applying/syncing the Blueprint in Render can create resources, deploy code, and incur charges.

## Proposed resources and cost
- Service: watchtower-guardian-staging, Python web service.
- Source: watchtower-Ai/Watchtower-Ai, branch watchtower-backend-v2.
- Region: Frankfurt. Confirm this region before creation; it cannot simply be changed later.
- Compute plan ID: 0.5c-512mb, currently listed at USD 7/month.
- Persistent disk: 1 GB at /var/data, currently USD 0.25/GB/month.
- Approximate baseline: USD 7.25/month for continuously provisioned compute plus disk,
  before taxes, workspace-plan fees, bandwidth/build overages or other account charges.
- This is not a free-tier configuration. Review Render's actual estimate before applying.
- No live AI calls are enabled by this Blueprint. Analysis-request limit starts at zero.

Pricing and supported Blueprint fields were checked on 2026-10-17:
https://render.com/pricing
https://render.com/docs/blueprint-spec
Rates and availability can change. This document does not authorize spending.

## Connect directly, without the Perplexity Render connector
1. Sign in to Render's website with your own account.
2. Choose New -> Blueprint, and authorize Render's GitHub integration if requested.
3. Select watchtower-Ai/Watchtower-Ai and explicitly select watchtower-backend-v2.
4. Use render.yaml at the repository root; review every proposed resource and region.
5. Use a new service. If a service with the proposed name already exists, stop and review
   whether the Blueprint would adopt/modify it; do not accidentally reconfigure it.
6. Disable automatic Blueprint syncing if offered. The file disables code auto-deploys and
   preview environments, but that does NOT stop initial deployment or explicit Blueprint syncs.
7. Check billing and exposure settings. Apply only if you approve the actual charges and access.
   Do not delete a service or disk as a troubleshooting shortcut: that can affect stored data.

## What the Blueprint does
- Installs the existing dashboard requirements and runs the two named unit-test suites.
- Starts Gunicorn using watchtower_web:create_app(), binding to Render's PORT.
- Runs one instance with one worker and two threads, appropriate for the bounded SQLite prototype.
- Places the SQLite database under the persistent disk mount, not the temporary source filesystem.
- Has Render generate the dashboard access token; the secret value is not stored in GitHub.
- Exposes /healthz for a basic liveness check, not proof of AI functionality or system safety.
- Disables automatic commit-triggered deployment and preview environments.

## First verification: synthetic data only
1. Check that the build tests pass and the service starts successfully.
2. Read WATCHTOWER_API_TOKEN in the service's Environment settings. Treat it as a secret.
   Never paste an OpenAI key into the website token field or into this chat.
3. Open the service URL, enter the DASHBOARD token and select Connect.
4. Select Add 5 synthetic records (no AI). Verify the API count and evidence entries change.
5. Redeploy manually after approval and confirm that records remain on the attached disk.
6. Keep WATCHTOWER_DAILY_ANALYSIS_LIMIT=0 and do not add provider credentials for this first test.

## Access and capability limitations
This creates a web service, not an automatically private website. The UI shell and /healthz
are reachable without the token; event API access requires the generated shared token.
Before storing anything sensitive, add suitable access restrictions/private access and review
rate limits, headers, retention, backups, dependency versions and the single-user auth design.
Use synthetic non-sensitive data only until that review. Do not publish the dashboard token.
The generated token gives API access, not separate operator/admin roles.
There is no image-assessment HTTP route, autonomous collector, tool blocking, deployed decoy,
independent shutdown service, or unrestricted RSI in this dashboard configuration.

## Enabling real text AI later requires a separate reviewed step
Configure OPENAI_API_KEY and a compatible OPENAI_MODEL only in Render's secret/environment
settings; set provider spending controls and a small permitted request limit before testing.
Then increase WATCHTOWER_DAILY_ANALYSIS_LIMIT deliberately and use an explicit analysis request.
Model input leaves the service and may incur cost. This configuration includes no provider key.

## Validation and remaining work
The YAML was parsed locally and key safety/configuration fields were checked. It was not
validated with Render's CLI/API, built on Render, deployed, or tested against a live model.
Review Render's Blueprint validation results before applying. /healthz is only liveness.
A successful commit is not a deployment; a successful deployment is not safety certification.
Dependency pinning/auditing and application security review remain outstanding for public use.
