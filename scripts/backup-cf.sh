#!/bin/bash
# Ежедневный бэкап контент-завода (instagram-automation): SQLite + медиа в Google Drive.
# На VPS установлен как /home/bidder/backup-cf.sh (в ДОМАШНЕЙ папке, как deploy.sh).
#
# Установка на VPS:
#   scp scripts/backup-cf.sh bidder@vps:~/backup-cf.sh && chmod +x ~/backup-cf.sh
#   crontab -e → 30 4 * * * /home/bidder/backup-cf.sh >> /home/bidder/backups/backup.log 2>&1
#
# Ротация: локально 3 дня, в Google Drive 14 дней. Медиа — инкрементально, без удалений.
set -Eeuo pipefail
DATA=/home/bidder/instagram-automation/data
DIR=/home/bidder/backups
REMOTE=gdrive:content-factory-backups
ENV=/home/bidder/wb-promotion/config/.env

# Молчаливый бэкап = не бэкап: о провале узнаём в Telegram, а не когда он понадобится.
notify() {
  local stamp="$DIR/.alert_stamp_cf" tok chat base
  [ -f "$stamp" ] && [ $(( $(date +%s) - $(stat -c %Y "$stamp") )) -lt 10800 ] && return 0
  tok=$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$ENV" 2>/dev/null | cut -d= -f2-) || true
  chat=$(grep -m1 '^TELEGRAM_CHAT_ID=' "$ENV" 2>/dev/null | cut -d= -f2-) || true
  base=$(grep -m1 '^TELEGRAM_API_BASE=' "$ENV" 2>/dev/null | cut -d= -f2-) || true
  [ -n "${tok:-}" ] && [ -n "${chat:-}" ] || return 0
  curl -sS -m 15 -X POST "${base:-https://api.telegram.org}/bot$tok/sendMessage" \
    -d chat_id="$chat" -d text="$1" >/dev/null 2>&1 || true
  touch "$stamp"
}
trap 'rm -f "${OUT:-}"; notify "🔴 Бэкап контент-завода НЕ сделан (backup-cf.sh, строка $LINENO). VPS биддера."' ERR

mkdir -p "$DIR"
TS=$(date +%Y%m%d-%H%M)
OUT="$DIR/content_factory-$TS.db"
# ВАЖНО: sqlite3 по несуществующему пути молча СОЗДАЁТ пустую базу, и .backup
# отдаёт валидный пустой файл — «успешный» бэкап ни о чём.
[ -f "$DATA/content_factory.db" ] || { notify "🔴 Базы контент-завода нет по пути $DATA/content_factory.db — бэкап не сделан."; exit 1; }
# консистентный снимок с учётом WAL
sqlite3 "$DATA/content_factory.db" ".backup '$OUT'"
# снимок сильно меньше боевой базы = битый/пустой, даже если sqlite3 вернул 0
SRC_SZ=$(stat -c %s "$DATA/content_factory.db"); OUT_SZ=$(stat -c %s "$OUT" 2>/dev/null || echo 0)
[ "$OUT_SZ" -ge $(( SRC_SZ / 2 )) ] || {
  rm -f "$OUT"
  notify "🔴 Бэкап контент-завода битый: снимок $OUT_SZ Б против боевой $SRC_SZ Б."
  exit 1
}
gzip -f "$OUT"
# локальная ротация: 3 дня
find "$DIR" -name "content_factory-*.db.gz" -mtime +3 -delete 2>/dev/null || true
# off-server: БД (ротация 14 дней) + конфиги + медиа (инкрементально, без удалений)
if rclone copy "$OUT.gz" "$REMOTE/db/" 2>>"$DIR/backup.log"; then
  # ротация в GD — ТОЛЬКО после удачной заливки, иначе сбой заливки
  # за две недели вычистит off-server копии, а новые не приедут
  rclone delete "$REMOTE/db/" --min-age 14d 2>>"$DIR/backup.log" || true
else
  echo "$(date) cf rclone db FAIL" >>"$DIR/backup.log"
  notify "🟠 Бэкап контент-завода сделан локально, но НЕ уехал в Google Drive."
fi
rclone copy "$DATA" "$REMOTE/data/" --exclude "content_factory.db*" --max-depth 1 2>>"$DIR/backup.log" || true
rclone copy "$DATA/media" "$REMOTE/data/media/" 2>>"$DIR/backup.log" || echo "$(date) cf rclone media FAIL" >>"$DIR/backup.log"
rclone copy "$DATA/product_refs" "$REMOTE/data/product_refs/" 2>>"$DIR/backup.log" || true
