#!/usr/bin/env bash
set -Eeuo pipefail

# Сохраняем доступ приложения к медиатому после обновления старого образа.
: "${PETSTORE_MEDIA_ROOT:=/var/lib/petstore/media}"
mkdir -p "${PETSTORE_MEDIA_ROOT}"
chown petstore:petstore "${PETSTORE_MEDIA_ROOT}"

# Один worker: ограничитель входа хранит состояние в памяти процесса.
exec setpriv --reuid=petstore --regid=petstore --init-groups \
  python -m uvicorn petstore.app:app --host 0.0.0.0 --port 8080 --workers 1 --no-access-log
