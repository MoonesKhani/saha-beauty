#!/usr/bin/env bash
# GitHub-hosted runner transport only. No production action without dispatch validation.
set -euo pipefail
umask 077
missing=()
[[ -n "${ARVAN_SSH_KEY:-}" ]] || missing+=(ARVAN_SSH_KEY)
[[ -n "${ARVAN_KNOWN_HOSTS:-}" ]] || missing+=(ARVAN_KNOWN_HOSTS)
if (( ${#missing[@]} )); then printf 'Unavailable secret in this queued run: %s\n' "${missing[@]}"; echo 'Start a NEW status workflow after saving repository secrets'; exit 1; fi
[[ "$ARVAN_HOST" =~ ^[a-zA-Z0-9.:-]+$ && "$ARVAN_USER" =~ ^[a-z_][a-z0-9_-]*$ && "$ARVAN_PORT" =~ ^[0-9]+$ ]] || exit 1
key="$RUNNER_TEMP/saha-deploy-key"
known="$RUNNER_TEMP/saha-known-hosts"
control="$RUNNER_TEMP/saha-deploy-control"
cleanup() {
  # Close only this job's private master; never leave a background SSH session.
  if [[ -S "$control" ]]; then
    timeout 5 ssh -F /dev/null -S "$control" -O exit -p "$ARVAN_PORT" "$ARVAN_USER@$ARVAN_HOST" >/dev/null 2>&1 || true
  fi
  rm -f "$key" "$known" "$control"
}
trap cleanup EXIT
python3 "$(dirname "$0")/prepare_ssh_key.py" --output "$key" --known-hosts-output "$known"
transport=(ssh -T -F /dev/null -o IPQoS=none -o Compression=no -o ControlMaster=auto -o ControlPersist=60 -o "ControlPath=$control" -i "$key" -p "$ARVAN_PORT" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=6 "$ARVAN_USER@$ARVAN_HOST")
report="$RUNNER_TEMP/deployment-report.json"
case "$OPERATION" in
  deploy)
    [[ "$REVISION" =~ ^[0-9a-f]{40}$ ]] || exit 1
    python3 "$(dirname "$0")/transfer_release.py" --attempt "${GITHUB_RUN_ID:?}-${GITHUB_RUN_ATTEMPT:?}" --bundle "$RUNNER_TEMP/release/release.tar" --commit "$REVISION" --report "$report" -- "${transport[@]}" ;;
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
