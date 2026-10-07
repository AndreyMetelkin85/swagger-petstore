#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_DB:=petstore}"
: "${POSTGRES_USER:=petstore}"
: "${POSTGRES_PASSWORD:=petstore}"
: "${PGDATA:=/var/lib/postgresql/data}"
: "${PETSTORE_MEDIA_ROOT:=/var/lib/petstore/media}"
: "${PETSTORE_DB_URL:=jdbc:postgresql://127.0.0.1:5432/${POSTGRES_DB}}"
: "${PETSTORE_DB_USER:=${POSTGRES_USER}}"
: "${PETSTORE_DB_PASSWORD:=${POSTGRES_PASSWORD}}"
: "${PETSTORE_EMBEDDED_MAIL:=true}"
export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD PGDATA
export PETSTORE_DB_URL PETSTORE_DB_USER PETSTORE_DB_PASSWORD
export PETSTORE_MEDIA_ROOT
mkdir -p "${PETSTORE_MEDIA_ROOT}"
chown petstore:petstore "${PETSTORE_MEDIA_ROOT}"

postgres_pid=""
api_pid=""
nginx_pid=""
mail_pid=""
shutdown() {
  trap - INT TERM EXIT
  for pid in "${nginx_pid}" "${mail_pid}"; do
    [[ -z "${pid}" ]] || kill -TERM "${pid}" 2>/dev/null || true
  done
  if [[ -n "${api_pid}" ]] && kill -0 "${api_pid}" 2>/dev/null; then
    kill -TERM "${api_pid}" 2>/dev/null || true
  fi
  if [[ -n "${postgres_pid}" ]] && kill -0 "${postgres_pid}" 2>/dev/null; then
    kill -TERM "${postgres_pid}" 2>/dev/null || true
  fi
  [[ -z "${api_pid}" ]] || wait "${api_pid}" 2>/dev/null || true
  [[ -z "${postgres_pid}" ]] || wait "${postgres_pid}" 2>/dev/null || true
  [[ -z "${nginx_pid}" ]] || wait "${nginx_pid}" 2>/dev/null || true
  [[ -z "${mail_pid}" ]] || wait "${mail_pid}" 2>/dev/null || true
}
trap shutdown INT TERM EXIT
mkdir -p "${PGDATA}" /var/run/postgresql
chown -R postgres:postgres "${PGDATA}" /var/run/postgresql
chmod 0700 "${PGDATA}"
setpriv --reuid=postgres --regid=postgres --init-groups \
  /usr/local/bin/docker-entrypoint.sh postgres \
  -c log_min_error_statement=panic -c log_error_verbosity=terse &
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

export FLYWAY_URL="jdbc:${PETSTORE_DB_URL#jdbc:}"
export FLYWAY_USER="${PETSTORE_DB_USER}"
export FLYWAY_PASSWORD="${PETSTORE_DB_PASSWORD}"
setpriv --reuid=petstore --regid=petstore --init-groups \
  /opt/flyway/flyway -locations=filesystem:/app/resources/db/migration \
  -baselineOnMigrate=true -baselineVersion=1 migrate
unset FLYWAY_PASSWORD

if [[ "${PETSTORE_EMBEDDED_MAIL}" == "true" ]]; then
  mkdir -p /smtp4dev
  chown -R petstore:petstore /smtp4dev
  export DOTNET_ROOT=/opt/dotnet DOTNET_CLI_HOME=/smtp4dev
  export ServerOptions__Urls=http://0.0.0.0:8025
  export ServerOptions__Port=2525 ServerOptions__ImapPort=1143
  export ServerOptions__HostName=mail.petstore.test ServerOptions__TlsMode=None
  export ServerOptions__DisableIPv6=true
  export ServerOptions__AuthenticationRequired=false ServerOptions__WebAuthenticationRequired=false
  export ServerOptions__DeliverMessagesToUsersDefaultMailbox=false
  export ServerOptions__NumberOfMessagesToKeep=500
  export ServerOptions__Mailboxes__0__Name=User1 ServerOptions__Mailboxes__0__Recipients=user1@petstore.test
  export ServerOptions__Mailboxes__1__Name=User2 ServerOptions__Mailboxes__1__Recipients=user2@petstore.test
  export ServerOptions__Mailboxes__2__Name=Tests ServerOptions__Mailboxes__2__Recipients='*'
  for index in 0 1 2; do
    user=user$((index + 1)); mailbox=User$((index + 1))
    if [[ "${index}" == "2" ]]; then user=tests; mailbox=Tests; fi
    export "ServerOptions__Users__${index}__Username=${user}"
    export "ServerOptions__Users__${index}__Password=mail-test-only"
    export "ServerOptions__Users__${index}__DefaultMailbox=${mailbox}"
  done
  export RelayOptions__SmtpServer='' RelayOptions__AutomaticRelayExpression=''
  export Serilog__MinimumLevel__Default=Warning
  (
    cd /opt/smtp4dev
    exec setpriv --reuid=petstore --regid=petstore --init-groups \
      python /usr/local/bin/petstore-run-mail.py
  ) &
  mail_pid=$!
  : "${PETSTORE_SMTP_HOST:=127.0.0.1}"
  : "${PETSTORE_SMTP_PORT:=2525}"
  export PETSTORE_SMTP_HOST PETSTORE_SMTP_PORT
fi
nginx -g 'daemon off;' &
nginx_pid=$!

# Exactly one API worker: the current login limiter and development JWT key are process-local.
setpriv --reuid=petstore --regid=petstore --init-groups \
  python -m uvicorn petstore.app:app --host 0.0.0.0 --port 8080 --workers 1 --no-access-log &
api_pid=$!
children=("${postgres_pid}" "${api_pid}" "${nginx_pid}")
[[ -z "${mail_pid}" ]] || children+=("${mail_pid}")
set +e
wait -n "${children[@]}"
status=$?
set -e
exit "${status}"
