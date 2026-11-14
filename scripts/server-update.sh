#!/usr/bin/env bash
# Update the existing Saha Compose deployment; never create/reset data or print .env.
set -euo pipefail
umask 077
# Artifact deployments reuse this updater, but never build or pull on production.
if [[ "${1:-}" == --release || "${1:-}" == --rollback || "${1:-}" == --status ]]; then
  mode="$1"; shift
  if [[ "$mode" == --status ]]; then
    exec python3 "$(dirname "$0")/deploy_release.py" --status "$@"
  fi
  exec python3 "$(dirname "$0")/deploy_release.py" "$@"
fi
command -v docker >/dev/null || { echo 'Docker در این سرور موجود نیست.' >&2; exit 1; }
docker compose version >/dev/null
if [[ $# -gt 0 ]]; then
  project_dir="$1"
else
  containers="$(docker ps --filter label=com.docker.compose.project=saha --filter label=com.docker.compose.service=app --format '{{.ID}}')"
  [[ -n "$containers" && "$containers" != *$'\n'* ]] || { echo 'پوشه پروژه را به‌عنوان آرگومان مشخص کنید؛ سرویس یکتای saha/app پیدا نشد.' >&2; exit 1; }
  project_dir="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$containers")"
fi
[[ -d "$project_dir" ]] || { echo 'پوشه پروژه پیدا نشد.' >&2; exit 1; }
cd "$project_dir"
[[ -f compose.yaml && -f .env && -d .git ]] || { echo 'compose.yaml، فایل خصوصی .env و مخزن موجود لازم‌اند؛ چیزی ساخته یا جایگزین نشد.' >&2; exit 1; }
# Distinguish an actual tracked change from a Git inspection failure. Ignored
# runtime files (.env, uploads and backups) and other untracked files are kept.
if ! repository_status="$(git status --porcelain=v1 --untracked-files=no)"; then
  echo 'بررسی وضعیت مخزن ناموفق بود؛ به‌روزرسانی انجام نشد.' >&2
  exit 1
fi
if [[ -n "$repository_status" ]]; then
  echo 'مخزن تغییر ذخیره‌نشده دارد؛ ابتدا تغییرات موجود را بررسی کنید.' >&2
  exit 1
fi
# Do not deploy from an unrelated remote or send credentials to a new destination.
remote="$(git remote get-url origin)"
case "$remote" in
  https://github.com/MoonesKhani/saha-beauty|https://github.com/MoonesKhani/saha-beauty.git|git@github.com:MoonesKhani/saha-beauty.git) ;;
  *) echo 'origin با مخزن تأییدشده سها مطابقت ندارد؛ متوقف شد.' >&2; exit 1;;
esac
mkdir -p .deploy
exec 9>.deploy/deploy.lock
flock -n 9 || { echo 'یک انتشار دیگر در حال اجراست.' >&2; exit 1; }
running="$(docker compose ps --status running --services)"
[[ $'\n'"$running"$'\n' == *$'\ndb\n'* && $'\n'"$running"$'\n' == *$'\napp\n'* ]] || { echo 'سرویس‌های موجود db و app باید فعال باشند؛ این اسکریپت نصب اولیه نیست.' >&2; exit 1; }
backup_dir="backups/update-$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
docker compose exec -T db pg_dump -U saha -d saha -Fc > "$backup_dir/database.dump"
docker compose exec -T app tar -C /app/var -czf - . > "$backup_dir/uploads.tar.gz"
[[ -s "$backup_dir/database.dump" && -s "$backup_dir/uploads.tar.gz" ]] || { echo 'پشتیبان معتبر ایجاد نشد؛ به‌روزرسانی متوقف شد.' >&2; exit 1; }
printf 'پشتیبان دیتابیس و فایل‌ها: %s\n' "$backup_dir"
git fetch origin main
git merge --ff-only origin/main
docker compose build app
docker compose run --rm --no-deps app python -m backend.app.cli init-db
docker compose up -d --no-deps app
curl --fail --silent --show-error --retry 15 --retry-connrefused --retry-delay 2 http://127.0.0.1:8000/api/v1/health/ready
printf '\nنسخه بک‌اند به‌روزرسانی شد. فایل .env، دیتابیس و volumeهای موجود حفظ شدند.\n'
printf 'نسخه کد: '; git rev-parse --short HEAD
