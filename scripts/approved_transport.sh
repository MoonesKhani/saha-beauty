#!/usr/bin/env bash
# GitHub-hosted runner transport only. No production action without dispatch validation.
set -euo pipefail
umask 077
missing=()
[[ -n "${ARVAN_SSH_KEY:-}" ]] || missing+=(ARVAN_SSH_KEY)
[[ -n "${ARVAN_KNOWN_HOSTS:-}" ]] || missing+=(ARVAN_KNOWN_HOSTS)
if [[ "${RELEASE_TRANSPORT:-arvan}" == arvan && ( "${OPERATION:-}" == deploy || "${OPERATION:-}" == otp-migration || "${OPERATION:-}" == artifact-probe ) ]]; then
  for secret_name in ARVAN_STORAGE_ACCESS_KEY_ID ARVAN_STORAGE_SECRET_ACCESS_KEY; do
    [[ -n "${!secret_name:-}" ]] || missing+=("$secret_name")
  done
fi
if (( ${#missing[@]} )); then printf 'Unavailable secret in this queued run: %s\n' "${missing[@]}"; echo 'Save the missing repository secrets, then start a NEW workflow; existing secret values were not changed'; exit 1; fi
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
common=(ssh -T -F /dev/null -o IPQoS=none -o Compression=no -i "$key" -p "$ARVAN_PORT" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
transport=("${common[@]}" -o ControlMaster=no -o "ControlPath=$control" "$ARVAN_USER@$ARVAN_HOST")
if [[ "$OPERATION" == deploy || "$OPERATION" == otp-migration || "$OPERATION" == rollback || "$OPERATION" == artifact-probe ]]; then
  # A dedicated master is detached from stdout/stderr pipes before any command.
  if ! timeout 25 "${common[@]}" -M -N -f -o ControlPersist=60 -o "ControlPath=$control" "$ARVAN_USER@$ARVAN_HOST" </dev/null >/dev/null 2>"$RUNNER_TEMP/saha-master-error"; then
    echo 'Verified SSH control connection failed; no installation requested' >&2; exit 1
  fi
fi
report="$RUNNER_TEMP/deployment-report.json"
case "$OPERATION" in
  artifact-probe)
    python3 "$(dirname "$0")/check_https_transfer.py" --bundle "$RUNNER_TEMP/https-probe/release.tar" -- "${transport[@]}"; exit 0 ;;
  probe)
    python3 "$(dirname "$0")/transfer_probe.py" --commit "$REVISION" -- "${transport[@]}"; exit 0 ;;
  deploy|otp-migration)
    extra=(--https-artifact)
    if [[ "${RELEASE_TRANSPORT:-arvan}" == arvan ]]; then extra=(--arvan-artifact);
    elif [[ "${RELEASE_TRANSPORT:-arvan}" != azure ]]; then echo 'Unsupported transfer backend; installation not requested' >&2; exit 1; fi
    if [[ "$OPERATION" == otp-migration ]]; then extra+=(--otp-migration); fi
    [[ "$REVISION" =~ ^[0-9a-f]{40}$ ]] || exit 1
    python3 "$(dirname "$0")/transfer_release.py" "${extra[@]}" --attempt "${GITHUB_RUN_ID:?}-${GITHUB_RUN_ATTEMPT:?}" --bundle "$RUNNER_TEMP/release/release.tar" --commit "$REVISION" --report "$report" -- "${transport[@]}" ;;
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
if os.environ['OPERATION'] in ('deploy','otp-migration') and current.get('commit')!=os.environ['REVISION']:raise SystemExit('Deployed commit mismatch')
if os.environ['OPERATION']=='rollback' and current['image_id']!=os.environ['REVISION']:raise SystemExit('Rollback image mismatch')
for record in [current,previous]:
 if not re.fullmatch(r'sha256:[0-9a-f]{64}',record['image_id']):raise SystemExit('Invalid report image identity')
with open(os.environ['GITHUB_OUTPUT'],'a') as output:
 output.write('image='+current['image_id']+'\nprevious_image='+previous['image_id']+'\n')
print(json.dumps({'phase':report['phase'],'current':current,'previous':previous},sort_keys=True))
PY
image="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["current"]["image_id"])' "$report")"
if [[ "$OPERATION" == deploy || "$OPERATION" == otp-migration ]]; then
  mkdir -p "$RUNNER_TEMP/site-image"
  tar -xf "$RUNNER_TEMP/release/release.tar" -C "$RUNNER_TEMP/site-image" manifest.json image.tar.gz
  python3 scripts/extract_release_site.py --bundle-dir "$RUNNER_TEMP/site-image" --target "$RUNNER_TEMP/pages" --image "$image" --commit "$REVISION"
  exit 0
fi
# OTP recovery is bundled: avoid transferring the static site back over slow SSH.
if [[ -f "$RUNNER_TEMP/release/release.tar" ]]; then
  mkdir -p "$RUNNER_TEMP/site-image"
  tar -xf "$RUNNER_TEMP/release/release.tar" -C "$RUNNER_TEMP/site-image" manifest.json image.tar.gz
  recovery_commit="$(python3 - "$RUNNER_TEMP/site-image/manifest.json" "$image" <<'PYCODE'
import json,sys
manifest=json.load(open(sys.argv[1]));records=[manifest,manifest.get('otp_recovery') or {}]
record=next((r for r in records if r.get('image_id')==sys.argv[2]),{})
print(record.get('commit',''))
PYCODE
)"
  if [[ -n "$recovery_commit" ]]; then
    python3 scripts/extract_release_site.py --bundle-dir "$RUNNER_TEMP/site-image" --target "$RUNNER_TEMP/pages" --image "$image" --commit "$recovery_commit"
    exit 0
  fi
fi
timeout 300 "${transport[@]}" "site $image" > "$RUNNER_TEMP/site.tar.gz"
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
