#!/usr/bin/env bash
# `stack.sh run` in containers: builds the images, starts compose.yaml's stack,
# runs the checks in the tests container, restarting MAS between groups as
# stack.sh does, then stops and removes everything.
set -euo pipefail

cd "$(dirname "$0")"
export GF_UID=${GF_UID:-$(id -u)} GF_GID=${GF_GID:-$(id -g)}

dc() { docker compose "$@"; }

dc down -v --remove-orphans
rm -rf state/maildir
mkdir -p state
trap 'dc logs --no-color >state/compose.log 2>&1; dc down -v' EXIT
dc up -d --build --wait

rc=0
check() { # script, log name
  dc run --rm -T tests python3 "$1" 2>&1 | tee "state/run-$2.log" || rc=1
}
restart_mas() {
  dc restart mas
  dc up -d --wait mas
}

check gf_browser.py browser
check gf_api.py api
# MAS's rate limits are in memory: a fresh process for the allowed-addresses group
restart_mas
check gf_allowed.py allowed
restart_mas
check gf_back.py back
exit "$rc"
