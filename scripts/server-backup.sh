#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
stamp="$(date -u +%Y%m%d-%H%M%S)"
docker compose exec -T db pg_dump -U saha -d saha -Fc > "backups/saha-$stamp.dump"
printf '%s\n' "پشتیبان دیتابیس ساخته شد: backups/saha-$stamp.dump" 'فایل‌های صوتی در volume جدا هستند و باید جداگانه پشتیبان‌گیری شوند.'
