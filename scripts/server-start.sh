#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Docker روی سرور نصب نیست؛ ابتدا Docker و افزونه Compose را نصب کنید.' >&2; exit 1; }
docker compose version >/dev/null
if [[ ! -f .env ]]; then
  umask 077
  temporary_env="$(mktemp .env.new.XXXXXX)"
  trap 'rm -f "$temporary_env"' EXIT
  docker run --rm python:3.12-slim python -c 'import secrets; print("POSTGRES_PASSWORD="+secrets.token_hex(32)); print("ADMIN_API_TOKEN="+secrets.token_hex(32)); print("SAHA_DOMAIN=sahabeauty.ir\nSAHA_BOOKING_ENABLED=0\nSAHA_AUDIO_UPLOADS=0")' > "$temporary_env"
  chmod 600 "$temporary_env"
  mv "$temporary_env" .env
  trap - EXIT
fi
if [[ -z "${SAHA_START_WITHOUT_WEB:-}" ]]; then
  docker compose up -d --build
else
  docker compose up -d --build db app
fi
printf '%s\n' 'کلید مدیریت فقط در فایل خصوصی .env روی سرور است؛ آن را در چت یا مخزن نفرستید.' 'رزرو تا ثبت برنامه واقعی و فعال‌کردن SAHA_BOOKING_ENABLED خاموش می‌ماند.' 'دامنه باید به این سرور برسد تا HTTPS و اتصال سایت کامل شود؛ CNAME تغییر نکرده است.'
