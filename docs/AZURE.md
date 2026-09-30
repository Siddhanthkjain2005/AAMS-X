# Azure judging deployment

AAMS-X serves the React frontend, FastAPI endpoints and live WebSockets from one Azure Container App in East Asia. The subscription's allowed-region policy determines the deployment region.

## Availability settings

- One minimum replica: the website does not intentionally scale down to zero.
- One maximum replica: limits compute exposure and keeps the in-memory experiment runtime on one instance.
- 1 vCPU and 2 GiB RAM.
- Public HTTPS ingress, port 8080 internally, insecure HTTP disabled.
- Startup, readiness and liveness probes use `/api/health`.
- A single active revision and an immutable commit-tagged image.

These settings reduce cold starts and allow the platform to replace unhealthy containers. They do not guarantee zero downtime. Maintain the student subscription and its credit balance. Ongoing compute and the Basic image registry can incur charges even when the demo is quiet. No optional Log Analytics workspace is configured.

## Stored data

Official TSRD and e-CALLISTO artifacts, simulation benchmarks and judging replays ship inside the image. The app restores those bundled artifacts after a restart. New live experiments use the container's local SQLite registry and compressed trace files. They are ephemeral and can disappear when a replica is replaced. Export new experiments before a restart. Durable storage and a shared database are future production work.

## Deployment security

The GitHub image workflow uses federated OIDC authentication. Its build identity has `AcrPush` access restricted to this demo's registry. The Azure app uses a separate managed identity with `AcrPull` on that registry. No registry password or cloud access token belongs in the repository.

## Operator checks

Public website: https://aams-x-sih.livelyocean-37549b44.eastasia.azurecontainerapps.io

Verified deployment image: `caf851fd20faacr.azurecr.io/aams-x:c32802a0997ca04fa4dc5fbd9695581433354e85`. The instance reports Running, ready, with zero restarts. Minimum and maximum replicas are both one. The public Chromium check passes all pages, stored TSRD evidence, CSV exports, replay, a real WebGL 2 renderer, a full 96-slot live TSRD run and mobile navigation without document-wide horizontal overflow. The replay HTTP payload measured 2,535,981 compressed bytes, compared with 14,235,411 before compression. These checks describe the validation session, not a future uptime guarantee.

To repeat the public browser check after installing frontend dependencies:

```sh
cd frontend
npx playwright install chromium
cd ..
node scripts/verify_deployed_demo.mjs \
  https://aams-x-sih.livelyocean-37549b44.eastasia.azurecontainerapps.io
```

This acceptance check starts a live experiment on the website and saves screenshots locally. Run it deliberately, rather than as an unbounded background monitor.

```sh
az containerapp show -g rg-aams-x-sih -n aams-x-sih \
  --query '{state:properties.provisioningState,url:properties.configuration.ingress.fqdn,scale:properties.template.scale}'
az containerapp revision list -g rg-aams-x-sih -n aams-x-sih -o table
```

The image-build workflow is manual. Publishing a new GitHub commit does not silently change the running Azure image. Build the selected commit, deploy its image and verify `/api/health`, `/api/status`, `/api/datasets`, benchmarks, exports and a live experiment before a judging session. The current Azure environment does not support custom revision suffixes. Use a normal image update and verify the resulting running image rather than adding unsupported revision options.

## Cost control

Review Azure Cost Management and student credit usage. Setting minimum replicas to zero saves idle compute but brings back cold starts. Deleting only the app does not remove registry charges. Removing the dedicated `rg-aams-x-sih` resource group removes this deployment's resources; do so only after saving required data and deliberately ending the demo.
