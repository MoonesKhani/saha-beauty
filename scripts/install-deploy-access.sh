#!/usr/bin/env bash
# One-time opt-in setup. Installs deployment access; does not restart app/db/web.
set -euo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo 'این نصب یک‌باره باید از Termius با root اجرا شود.' >&2; exit 1; }
project_dir="$(cd "${1:?مسیر پروژه فعلی لازم است}" && pwd -P)"
source_dir="$(cd "$(dirname "$0")" && pwd -P)"
[[ -f "$project_dir/compose.yaml" && -f "$project_dir/.env" ]] || { echo 'استقرار موجود پیدا نشد؛ چیزی نصب نشد.' >&2; exit 1; }
for command in docker python3 systemd-run ssh-keygen; do command -v "$command" >/dev/null; done
docker compose version >/dev/null
python3 - "$project_dir" <<'PY_CHECK'
import json,sys
from pathlib import Path
if sys.version_info < (3,8):raise SystemExit('Python 3.8+ is required')
path=Path('/opt/saha-deploy/config.json')
if path.exists() and json.loads(path.read_text())['project']!=sys.argv[1]:raise SystemExit('مسیر نصب قبلی متفاوت است؛ چیزی تغییر نکرد.')
PY_CHECK
architecture="$(docker info --format '{{.Architecture}}')"
[[ "$architecture" == x86_64 || "$architecture" == amd64 ]] || { echo 'ساخت image فعلی برای amd64 است؛ ابتدا پشتیبانی معماری این سرور باید اضافه شود.' >&2; exit 1; }
mkdir -p "$project_dir/.deploy"
exec 9>"$project_dir/.deploy/deploy.lock"
flock -n 9 || { echo 'یک انتشار در حال اجراست؛ نصب انجام نشد.' >&2; exit 1; }
install -d -m 700 /opt/saha-deploy
for file in server-update.sh deploy_release.py deploy_receiver.py; do install -m 700 "$source_dir/$file" "/opt/saha-deploy/$file"; done
python3 - "$project_dir" <<'PY'
import json,os,sys
from pathlib import Path
path=Path('/opt/saha-deploy/config.json')
if path.exists() and json.loads(path.read_text())['project']!=sys.argv[1]:raise SystemExit('مسیر نصب قبلی متفاوت است؛ تنظیمات موجود بازنویسی نشد.')
path.write_text(json.dumps({'project':sys.argv[1]})+'\n');os.chmod(path,0o600)
PY
install -d -m 700 /root/.ssh
key=/root/.ssh/saha-actions-deploy
if [[ ! -f "$key" && ! -f "$key.pub" ]]; then ssh-keygen -q -t ed25519 -N '' -C saha-github-deploy -f "$key"; fi
[[ -f "$key" && -f "$key.pub" ]] || { echo 'فایل‌های کلید قبلی ناقص‌اند؛ بازنویسی نشدند.' >&2; exit 1; }
ssh-keygen -y -f "$key" > /opt/saha-deploy/deploy-key.pub
entry="restrict,command=\"python3 /opt/saha-deploy/deploy_receiver.py\" $(cat /opt/saha-deploy/deploy-key.pub) saha-github-deploy"
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys "$key"
python3 - "$entry" <<'PY_KEY'
from pathlib import Path
import sys
path=Path('/root/.ssh/authorized_keys');data=path.read_bytes();entry=sys.argv[1].encode();public=Path('/opt/saha-deploy/deploy-key.pub').read_bytes().split()[:2]
needle=b' '.join(public)
if any(needle in line and line!=entry for line in data.splitlines()):raise SystemExit('این کلید با دسترسی دیگری ثبت شده است؛ کلیدهای موجود تغییر نکردند.')
if entry not in data.splitlines():
 with path.open('ab') as target:
  if data and not data.endswith(b'\n'):target.write(b'\n')
  target.write(entry+b'\n')
PY_KEY
awk '{print "37.32.39.8 "$1" "$2}' /etc/ssh/ssh_host_ed25519_key.pub > /opt/saha-deploy/github-known-hosts
printf '%s\n' 'دسترسی انتشار نصب شد؛ سرویس‌های سایت تغییر نکردند.' 'در GitHub Secrets:' 'ARVAN_SSH_KEY = محتوای فایل /root/.ssh/saha-actions-deploy' 'ARVAN_KNOWN_HOSTS = محتوای فایل /opt/saha-deploy/github-known-hosts' 'کلید خصوصی را در چت، Git یا لاگ‌ها قرار ندهید.'
