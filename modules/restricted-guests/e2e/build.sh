#!/usr/bin/env bash
# Builds what stack.sh runs into work/: mas-cli with the assets it reads at
# runtime, and a development build of Element Web with the restricted-guests
# module.
#
#   build.sh [mas] [element-web]   (default: both)
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${GF_WORK:-$HERE/work}
MAS_SRC=${GF_MAS_SRC:-$HERE/src/mas}
ELEMENT_WEB_SRC=${GF_ELEMENT_WEB_SRC:-$HERE/src/element-web}

build_mas() {
  cd "$MAS_SRC"
  cargo build -p mas-cli
  pnpm install --frozen-lockfile --no-runtime
  pnpm --filter mas-frontend run build
  make -C policies
  rm -rf "$WORK/mas"
  mkdir -p "$WORK/mas/frontend" "$WORK/mas/policies"
  cp "${CARGO_TARGET_DIR:-target}/debug/mas-cli" "$WORK/mas-cli"
  cp -r templates translations "$WORK/mas/"
  cp -r frontend/dist "$WORK/mas/frontend/"
  cp policies/policy.wasm "$WORK/mas/policies/"
}

build_element-web() {
  cd "$ELEMENT_WEB_SRC"
  pnpm install --frozen-lockfile
  NX_DAEMON=false NX_NO_CLOUD=true ./node_modules/.bin/nx run-many -t build \
    -p @element-hq/web-shared-components @element-hq/element-web-module-api @element-hq/element-web-module-restricted-guests
  (cd apps/web && NODE_OPTIONS=--max-old-space-size=4096 ./node_modules/.bin/webpack-cli --mode development)
  mkdir -p apps/web/webapp/modules/restricted-guests
  cp modules/restricted-guests/lib/* apps/web/webapp/modules/restricted-guests/
  mkdir -p "$WORK"
  ln -sfn "$PWD/apps/web/webapp" "$WORK/webapp"
}

parts=("$@")
[ ${#parts[@]} -gt 0 ] || parts=(mas element-web)
for p in "${parts[@]}"; do "build_$p"; done
