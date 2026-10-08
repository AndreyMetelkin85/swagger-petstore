#!/usr/bin/env bash
set -Eeuo pipefail

# Сохраняем доступ приложения к медиатому после обновления старого образа.
: "${PETSTORE_MEDIA_ROOT:=/var/lib/petstore/media}"
task_media_root=$(realpath -m -- "${PETSTORE_MEDIA_ROOT}")
case "${task_media_root}" in
  /|/app|/var|/var/lib|/var/lib/petstore|/etc|/usr|/home|/tmp)
    echo 'Отказ изменения владельца системного каталога' >&2
    exit 1 ;;
esac
mkdir -p "${PETSTORE_MEDIA_ROOT}"
# UID 998 совместим со старым образом; восстанавливаем права и файлов, созданных UID 999.
chown --no-dereference -R petstore:petstore "${task_media_root}"

# Один worker: ограничитель входа хранит состояние в памяти процесса.
exec setpriv --reuid=petstore --regid=petstore --init-groups \
  python -m uvicorn petstore.app:app --host 0.0.0.0 --port 8080 --workers 1 --no-access-log
