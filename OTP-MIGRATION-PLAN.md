
### Finalize the existing Nginx origin and live OTP (owner-authorized)

The main domain can terminate at host Nginx rather than Pages. A successful Pages
upload must not be treated as proof that this origin serves the same release.
`prepare-live-otp.py --apply` is a one-time root/Termius preparation using the
existing restricted-access config and Compose project. It requires the already
installed `0005_auth_sms` schema and healthy recorded image. It validates the
existing server secrets without printing or replacing them, backs up DB/uploads
and private configuration, identifies exactly one HTTPS vhost for sahabeauty.ir,
and syntax-tests/reloads only that Nginx configuration. Ambiguous routing stops
before changes. Existing API proxy directives are retained.

For a server-level static root, Nginx uses `/var/lib/saha-release/current`.
A full-site loopback reverse proxy is retained. The exact `/release.json` route
uses the same versioned public directory. After health and actual-image checks,
ComposeEngine exports that running app's built frontend and atomically selects
its directory, including release identity. Rollback selects the matching old
frontend too. No standalone version stamp can hide stale frontend files.

The existing private OTP Compose overlay overrides the old disabled gates with
OTP/live/contract=1, TTL=120; notification/template gates stay 0. No keys are
created, `.env` stays unchanged, and no provider request is made. Preparation
retains the current recovery image; the next ordinary approved **deploy** of
f1defac (not another schema migration) activates the existing OTP implementation.
A configuration failure restores the old app/settings, never live data. A failed
recovery is reported explicitly. Once prepared, use the existing workflow with
operation=deploy, revision=f1defacf8f0041de054cd82211fc1ce65df12ab9,
build_run_id=43957281129 and its exact DEPLOY confirmation. Verify both workflow
results and public readiness/capabilities/version via GET only. Do not test SMS
by posting to OTP/request without separate authorization to send a message.
