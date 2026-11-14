#!/bin/bash
# ============================================================
# YANGI TANLOV UCHUN BAZANI TO'LIQ TOZALASH
#
# O'CHIRILADI: foydalanuvchilar (bloklanganlar ham), to'lovlar, ishtirokchilar,
#              natijalar, javoblar, test vaqti va eslatma belgisi.
# QOLADI:      "ro'yxatdan o'tish" va "to'lov" yopiq/ochiq holati (o'zgartirilmaydi).
#
# Ishga tushirish:   bash deploy_scripts/reset_contest.sh
# Avval avtomatik zaxira oladi (zaxira olinmasa, HECH NARSA O'CHIRILMAYDI).
# Keyin tasdiq so'raydi: TOZALASH deb yozish kerak.
# ============================================================
set -uo pipefail

CONTAINER_NAME="kitobxonlik_postgres"
DB_USER="bek_user"
DB_NAME="kitobxonlik_db"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

psql_run() { docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 "$@"; }

echo "=== Hozirgi holat ==="
psql_run -c "SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM payments) AS payments, (SELECT count(*) FROM participants) AS participants, (SELECT count(*) FROM results) AS results, (SELECT count(*) FROM user_answers) AS user_answers;" || { echo "❌ Bazaga ulanib bo'lmadi. To'xtatildi."; exit 1; }

echo
echo "Bu buyruq yuqoridagi HAMMA ma'lumotni o'chiradi."
read -r -p "Davom etish uchun TOZALASH deb yozing: " ANSWER
if [ "$ANSWER" != "TOZALASH" ]; then echo "Bekor qilindi. Hech narsa o'chirilmadi."; exit 0; fi

echo "=== 1/3 Zaxira olinmoqda ==="
if ! bash "$HERE/backup.sh"; then echo "❌ Zaxira olinmadi. HECH NARSA O'CHIRILMADI."; exit 1; fi

mkdir -p /root/arxiv_1-tanlov
LATEST="$(ls -t "$HERE"/../backups/kitobxonlik_backup_*.sql.gz | head -1)"
cp "$LATEST" "/root/arxiv_1-tanlov/oldin_tozalash_$(basename "$LATEST")"
echo "Arxivga nusxalandi: /root/arxiv_1-tanlov/oldin_tozalash_$(basename "$LATEST")"

echo "=== 2/3 Tozalanmoqda ==="
psql_run <<'SQL'
BEGIN;
TRUNCATE TABLE user_answers, results, participants, payments, users RESTART IDENTITY CASCADE;
DELETE FROM settings WHERE key IN ('test_start_time', 'reminder_last_date');
COMMIT;
SQL
if [ $? -ne 0 ]; then echo "❌ Tozalashda xato. O'zgarish bekor qilindi (tranzaksiya)."; exit 1; fi

echo "=== 3/3 Natija ==="
psql_run -c "SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM payments) AS payments, (SELECT count(*) FROM participants) AS participants, (SELECT count(*) FROM results) AS results, (SELECT count(*) FROM user_answers) AS user_answers;"
psql_run -c "SELECT key, value FROM settings ORDER BY key;"
echo "✅ Tayyor. Hammasi 0 bo'lishi kerak."