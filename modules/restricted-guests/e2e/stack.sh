#!/usr/bin/env bash
# The stack for the guest flows check, run locally: a mail sink, Synapse with
# the guest module, MAS and Element Web on :8090. build.sh builds what it runs.
#
#   stack.sh reset           recreate both databases and empty the mailbox
#   stack.sh start [part…]   start sink, synapse, mas and/or element (default: all)
#   stack.sh stop  [part…]   (default: all)
#   stack.sh run             stop, reset, start all, run gf_browser.py and gf_api.py,
#                            restart MAS, run gf_allowed.py, restart MAS, run gf_back.py, stop
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
STATE=$HERE/state
WORK=${GF_WORK:-$HERE/work}
MODULE_SRC=${GF_MODULE_SRC:-$HERE/../synapse}
PYTHON=${GF_PYTHON:-python3} # with requirements.txt and matrix-synapse[postgres] installed
export GF_WEBAPP=$WORK/webapp
export PGHOST=${PGHOST:-localhost} PGPORT=${PGPORT:-5432} PGUSER=${PGUSER:-postgres} PGPASSWORD=${PGPASSWORD:-postgres}

unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
mkdir -p "$STATE"

wait_for() { # name, command
  for _ in $(seq 120); do
    eval "$2" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "$1 didn't come up; see $STATE/$1.log" >&2
  return 1
}

write_configs() {
  cat >"$STATE/homeserver.yaml" <<EOF
database:
  name: psycopg2
  args:
    host: "$PGHOST"
    port: $PGPORT
    user: "$PGUSER"
    password: "$PGPASSWORD"
    database: gf_synapse
    cp_min: 1
    cp_max: 5
media_store_path: "$STATE/media_store"
signing_key_path: "$STATE/localhost.signing.key"
EOF
  cat >"$STATE/mas.yaml" <<EOF
database:
  uri: "postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/gf_mas"
EOF
}

start_sink() {
  "$PYTHON" -m aiosmtpd -n -l localhost:1025 \
    -c aiosmtpd.handlers.Mailbox "$STATE/maildir" >"$STATE/sink.log" 2>&1 &
  echo $! >"$STATE/sink.pid"
  wait_for sink "echo >/dev/tcp/127.0.0.1/1025"
}

# The module comes from MODULE_SRC, ahead of any installed copy
start_synapse() {
  write_configs
  local config=(-c "$HERE/config/homeserver.yaml" -c "$STATE/homeserver.yaml")
  [ -f "$STATE/localhost.signing.key" ] ||
    PYTHONPATH=$MODULE_SRC "$PYTHON" -m synapse.app.homeserver "${config[@]}" --generate-keys
  PYTHONPATH=$MODULE_SRC "$PYTHON" -m synapse.app.homeserver "${config[@]}" >>"$STATE/synapse.log" 2>&1 &
  echo $! >"$STATE/synapse.pid"
  wait_for synapse "curl -sf http://localhost:8008/_matrix/client/versions"
}

# MAS reads its templates, translations, frontend and policy relative to WORK/mas
start_mas() {
  write_configs
  [ -f "$STATE/mas-config.generated.yaml" ] ||
    "$WORK/mas-cli" config generate -o "$STATE/mas-config.generated.yaml"
  cd "$WORK/mas"
  "$WORK/mas-cli" server -c "$STATE/mas-config.generated.yaml" -c "$HERE/config/mas-config.yaml" -c "$STATE/mas.yaml" \
    >>"$STATE/mas.log" 2>&1 &
  echo $! >"$STATE/mas.pid"
  wait_for mas "curl -sf http://localhost:8080/.well-known/openid-configuration && curl -s http://localhost:8082/"
}

start_element() {
  "$PYTHON" "$HERE/element_serve.py" "$GF_WEBAPP" "$HERE/config/element-config.json" 8090 \
    >"$STATE/element.log" 2>&1 &
  echo $! >"$STATE/element.pid"
  wait_for element "curl -sf http://localhost:8090/config.json"
}

stop_part() {
  local pidfile=$STATE/$1.pid
  [ -f "$pidfile" ] || return 0
  local pid
  pid=$(cat "$pidfile")
  if kill "$pid" 2>/dev/null; then
    for _ in $(seq 30); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pidfile"
}

reset() {
  for db in gf_synapse gf_mas; do
    psql -d postgres -q -v ON_ERROR_STOP=1 \
      -c "DROP DATABASE IF EXISTS $db" \
      -c "CREATE DATABASE $db TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C' ENCODING 'UTF8'"
  done
  rm -rf "$STATE/maildir" "$STATE/media_store"
  rm -f "$STATE/synapse.log" "$STATE/mas.log"
}

all_down() { for p in element mas synapse sink; do stop_part "$p"; done; }

cmd=${1:-}
shift || true
parts=("$@")

case $cmd in
  start)
    [ ${#parts[@]} -gt 0 ] || parts=(sink synapse mas element)
    for p in "${parts[@]}"; do "start_$p"; done
    ;;
  stop)
    [ ${#parts[@]} -gt 0 ] || parts=(element mas synapse sink)
    for p in "${parts[@]}"; do stop_part "$p"; done
    ;;
  reset) reset ;;
  run)
    all_down
    reset
    trap all_down EXIT
    for p in sink synapse mas element; do "start_$p"; done
    rc=0
    "$PYTHON" "$HERE/gf_browser.py" 2>&1 | tee "$STATE/run-browser.log" || rc=1
    "$PYTHON" "$HERE/gf_api.py" 2>&1 | tee "$STATE/run-api.log" || rc=1
    # MAS's rate limits are in memory: a fresh process for the allowed-addresses group
    stop_part mas
    start_mas
    "$PYTHON" "$HERE/gf_allowed.py" 2>&1 | tee "$STATE/run-allowed.log" || rc=1
    stop_part mas
    start_mas
    "$PYTHON" "$HERE/gf_back.py" 2>&1 | tee "$STATE/run-back.log" || rc=1
    exit "$rc"
    ;;
  *)
    sed -n '2,10p' "$0"
    exit 2
    ;;
esac
