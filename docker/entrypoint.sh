#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_DB:=petstore}"
: "${POSTGRES_USER:=petstore}"
: "${POSTGRES_PASSWORD:=petstore}"
: "${PGDATA:=/var/lib/postgresql/data}"

: "${PETSTORE_DB_URL:=jdbc:postgresql://127.0.0.1:5432/${POSTGRES_DB}}"
: "${PETSTORE_DB_USER:=${POSTGRES_USER}}"
: "${PETSTORE_DB_PASSWORD:=${POSTGRES_PASSWORD}}"

export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD PGDATA
export PETSTORE_DB_URL PETSTORE_DB_USER PETSTORE_DB_PASSWORD

postgres_pid=""
api_pid=""

# Invoked indirectly by the signal and exit traps below.
# shellcheck disable=SC2329
shutdown() {
  trap - INT TERM EXIT

  if [[ -n "${api_pid}" ]] && kill -0 "${api_pid}" 2>/dev/null; then
    kill -TERM "${api_pid}" 2>/dev/null || true
  fi
  if [[ -n "${postgres_pid}" ]] && kill -0 "${postgres_pid}" 2>/dev/null; then
    kill -TERM "${postgres_pid}" 2>/dev/null || true
  fi

  [[ -z "${api_pid}" ]] || wait "${api_pid}" 2>/dev/null || true
  [[ -z "${postgres_pid}" ]] || wait "${postgres_pid}" 2>/dev/null || true
}

trap shutdown INT TERM EXIT

mkdir -p "${PGDATA}" /var/run/postgresql
chown -R postgres:postgres "${PGDATA}" /var/run/postgresql
chmod 0700 "${PGDATA}"

setpriv --reuid=postgres --regid=postgres --init-groups \
  /usr/local/bin/docker-entrypoint.sh postgres &
postgres_pid=$!

database_ready=false
for _ in $(seq 1 90); do
  if pg_isready -h 127.0.0.1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    database_ready=true
    break
  fi
  if ! kill -0 "${postgres_pid}" 2>/dev/null; then
    wait "${postgres_pid}"
    exit $?
  fi
  sleep 1
done

if [[ "${database_ready}" != "true" ]]; then
  echo "PostgreSQL did not become ready within 90 seconds" >&2
  exit 1
fi

setpriv --reuid=petstore --regid=petstore --init-groups \
  /usr/local/tomcat/bin/catalina.sh run &
api_pid=$!

set +e
wait -n "${postgres_pid}" "${api_pid}"
status=$?
set -e

exit "${status}"
