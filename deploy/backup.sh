#!/bin/sh
# Consistent copy of the live database (safe while a game is running), kept for 14 days.
set -eu
umask 077
DB="${QUIZBLITZ_DB:-/var/lib/quizblitz/quizblitz.db}"
DIR="${QUIZBLITZ_BACKUP_DIR:-/var/lib/quizblitz/backups}"
mkdir -p "$DIR"
OUT="$DIR/quizblitz-$(date +%Y%m%d-%H%M%S).db"
sqlite3 "$DB" ".timeout 10000" ".backup '$OUT'"
test "$(sqlite3 "$OUT" 'PRAGMA integrity_check')" = ok
gzip "$OUT"
find "$DIR" -name 'quizblitz-*.db.gz' -mtime +14 -delete
