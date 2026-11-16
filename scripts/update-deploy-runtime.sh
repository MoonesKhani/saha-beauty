#!/usr/bin/env bash
# Upgrade only installed deployment helpers; never create keys/restart services.
set -euo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo 'Run as root from Termius.' >&2; exit 1; }
source_dir="$(cd "$(dirname "$0")" && pwd -P)"
[[ -f /opt/saha-deploy/config.json ]] || { echo 'Existing deployment access is required; nothing changed.' >&2; exit 1; }
project_dir="$(python3 - <<'PY'
import json
from pathlib import Path
print(Path(json.loads(Path('/opt/saha-deploy/config.json').read_text())['project']).resolve())
PY
)"
[[ -f "$project_dir/compose.yaml" && -f "$project_dir/.env" && -d "$project_dir/.deploy" ]] || { echo 'Existing project/configuration missing; nothing changed.' >&2; exit 1; }
# Check all replacements before changing any installed file.
python3 - "$source_dir" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
for name in ['deploy_release.py','artifact_fetch.py','deploy_otp_migration.py','deploy_receiver.py']:
 compile((root/name).read_bytes(),str(root/name),'exec')
PY
bash -n "$source_dir/server-update.sh"
exec 9>"$project_dir/.deploy/deploy.lock"
flock -n 9 || { echo 'A deployment is running; helpers NOT updated.' >&2; exit 1; }
active_units="$(systemctl list-units --plain --no-legend --state=activating,active,deactivating 'saha-release-*')"
[[ -z "$active_units" ]] || { echo 'A release service is active; wait and read status first. Nothing changed.' >&2; exit 1; }
backup_dir="$(mktemp -d /opt/saha-deploy/runtime-backup.XXXXXX)"
for file in server-update.sh deploy_release.py artifact_fetch.py deploy_otp_migration.py deploy_receiver.py; do
  if [[ -f "/opt/saha-deploy/$file" ]]; then cp -p "/opt/saha-deploy/$file" "$backup_dir/$file"; fi
  install -m 700 "$source_dir/$file" "/opt/saha-deploy/$file.new"
done
for file in server-update.sh deploy_release.py artifact_fetch.py deploy_otp_migration.py deploy_receiver.py; do mv -f "/opt/saha-deploy/$file.new" "/opt/saha-deploy/$file"; done
printf '%s\n' 'Deployment helpers upgraded to verified transfer protocol 3 (HTTPS artifacts).' "Previous helpers: $backup_dir" 'App, database, uploads, .env, authorized_keys and GitHub Secrets were not changed.'
