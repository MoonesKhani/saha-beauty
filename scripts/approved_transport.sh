#!/usr/bin/env bash
# GitHub-hosted runner transport only. No production action without dispatch validation.
set -euo pipefail
umask 077
[[ -n "${ARVAN_SSH_KEY:-}" && -n "${ARVAN_KNOWN_HOSTS:-}" ]] || { echo 'Configure ARVAN_SSH_KEY and ARVAN_KNOWN_HOSTS first'; exit 1; }
[[ "$ARVAN_HOST" =~ ^[a-zA-Z0-9.:-]+$ && "$ARVAN_USER" =~ ^[a-z_][a-z0-9_-]*$ && "$ARVAN_PORT" =~ ^[0-9]+$ ]] || exit 1
key="$RUNNER_TEMP/saha-deploy-key"
known="$RUNNER_TEMP/saha-known-hosts"
trap 'rm -f "$key" "$known"' EXIT
printf '%s\n' "$ARVAN_SSH_KEY" > "$key"
printf '%s\n' "$ARVAN_KNOWN_HOSTS" > "$known"
ssh-keygen -y -f "$key" > /dev/null
transport=(ssh -F /dev/null -i "$key" -p "$ARVAN_PORT" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=6 "$ARVAN_USER@$ARVAN_HOST")
report="$RUNNER_TEMP/deployment-report.json"
case "$OPERATION" in
  deploy)
    [[ "$REVISION" =~ ^[0-9a-f]{40}$ ]] || exit 1
    cat "$RUNNER_TEMP/release/release.tar" | "${transport[@]}" "deploy $REVISION" > "$report" ;;
  rollback)
    [[ "$REVISION" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1
    "${transport[@]}" "rollback $REVISION" > "$report" ;;
  status) "${transport[@]}" status; exit 0 ;;
  *) exit 1 ;;
esac
python3 - "$report" <<'PY'
import json,os,re,sys
from pathlib import Path
report=json.loads(Path(sys.argv[1]).read_text())
if report.get('phase')!='healthy':raise SystemExit('A healthy completed transaction is required')
current=report['current'];previous=report['previous']
if os.environ['OPERATION']=='deploy' and current.get('commit')!=os.environ['REVISION']:raise SystemExit('Deployed commit mismatch')
if os.environ['OPERATION']=='rollback' and current['image_id']!=os.environ['REVISION']:raise SystemExit('Rollback image mismatch')
for record in [current,previous]:
 if not re.fullmatch(r'sha256:[0-9a-f]{64}',record['image_id']):raise SystemExit('Invalid report image identity')
with open(os.environ['GITHUB_OUTPUT'],'a') as output:
 output.write('image='+current['image_id']+'\nprevious_image='+previous['image_id']+'\n')
print(json.dumps({'phase':report['phase'],'current':current,'previous':previous},sort_keys=True))
PY
image="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["current"]["image_id"])' "$report")"
"${transport[@]}" "site $image" > "$RUNNER_TEMP/site.tar.gz"
python3 - "$RUNNER_TEMP/site.tar.gz" "$RUNNER_TEMP/pages" <<'PY'
import json,os,sys,tarfile
from pathlib import Path,PurePosixPath
source=Path(sys.argv[1]);target=Path(sys.argv[2]);target.mkdir()
with tarfile.open(source,'r:gz') as archive:
 members=archive.getmembers()
 if sum(m.size for m in members)>100*1024**2:raise SystemExit('Site archive too large')
 for item in members:
  path=PurePosixPath(item.name)
  if path.is_absolute() or '..' in path.parts or not (item.isdir() or item.isfile()):raise SystemExit('Unsafe site archive')
 archive.extractall(target,filter='data')
expected=json.loads(Path(os.environ['RUNNER_TEMP']+'/deployment-report.json').read_text())['current']['image_id']
if json.loads((target/'release.json').read_text())['image_id']!=expected:raise SystemExit('Site image mismatch')
PY
