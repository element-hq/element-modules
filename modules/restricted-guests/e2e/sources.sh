#!/usr/bin/env bash
# Fetches the MAS and Element Web sources under test into src/. The Synapse
# module under test is this checkout's.
#
#   GF_MAS_BRANCHES       MAS branches, merged in order
#   GF_ELEMENT_WEB_REF    Element Web commit, branch or tag
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$HERE/src
MAS_BRANCHES=(${GF_MAS_BRANCHES:-quenting/guest-invite-link-design devonh/skip-consent})
ELEMENT_WEB_REF=${GF_ELEMENT_WEB_REF:-aea209b6bf639ff830fa2aab0d870b47fc78f55e}

clone() { # url, dir
  [ -d "$2" ] || git clone --filter=blob:none --no-checkout "$1" "$2"
}

mkdir -p "$SRC"

clone https://github.com/element-hq/matrix-authentication-service "$SRC/mas"
git -C "$SRC/mas" fetch origin "+refs/heads/${MAS_BRANCHES[0]}"
git -C "$SRC/mas" -c advice.detachedHead=false checkout -f FETCH_HEAD
for branch in "${MAS_BRANCHES[@]:1}"; do
  git -C "$SRC/mas" fetch origin "+refs/heads/$branch"
  git -C "$SRC/mas" -c user.name=e2e -c user.email=e2e@localhost merge --no-edit FETCH_HEAD
done

clone https://github.com/element-hq/element-web "$SRC/element-web"
git -C "$SRC/element-web" fetch origin "$ELEMENT_WEB_REF"
git -C "$SRC/element-web" -c advice.detachedHead=false checkout -f FETCH_HEAD
