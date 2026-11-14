# Production release policy

- Use the existing checkout and Docker/Compose deployment. Prepare changes on a branch/PR and run the existing CI. Do not push directly to main, merge, dispatch a production deployment, change Pages source or install server access without the user's applicable approval.
- The user chose approval in the Codex conversation. Before a production dispatch, identify the exact main commit and successful CI run and obtain explicit approval for that release. If the user has already explicitly approved that identified release, proceed without asking again.
- Follow DEPLOY-AUTOMATION.md. Production deploy.yml is workflow_dispatch-only. Never add push, PR or workflow_run production triggers or dispatch from a preparation/CI job. CI success alone is not production approval.
- Deploy only the verified artifact for the approved SHA. Do not build/pull images on Arvan. Use scripts/server-update.sh artifact mode through the installed restricted receiver. Preserve the existing Compose project, .env, PostgreSQL and upload volumes.
- Never reset/clean the production checkout, delete production volumes, restore live data automatically, or print .env/private keys. Disposable UUID-named Docker integration-test volumes are the only volumes removed by tests.
- Schema-changing releases require a separate reviewed migration/recovery plan. Do not bypass the database revision guard to make a release pass.
- Check both server and Pages workflow results. On uncertain SSH delivery, request read-only status before retrying. Report failed rollback or incomplete activation honestly; do not claim a live deployment from a successful build or Git push.
