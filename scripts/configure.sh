#!/bin/sh
# Edit hefaistos targets in the terminal, then install config.json on the NAS and restart it.
#
# From .env next to compose.yaml (or the environment):
#   HEFAISTOS_CONFIG_DIR  the config folder as mounted on this machine
#   QNAP_TARGET           ssh target, e.g. admin@192.168.0.10
#   REMOTE_DIR            the deploy folder (with compose.yaml) as seen on the QNAP
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/env.sh"
load_env "$root/.env"
: "${HEFAISTOS_CONFIG_DIR:?set HEFAISTOS_CONFIG_DIR in .env to the config folder as mounted here}"
: "${QNAP_TARGET:?set QNAP_TARGET in .env, e.g. admin@192.168.0.10}"
: "${REMOTE_DIR:?set REMOTE_DIR in .env to the deploy folder path on the QNAP}"
[ -d "$HEFAISTOS_CONFIG_DIR" ] || { echo "$HEFAISTOS_CONFIG_DIR not found; mount the NAS share first" >&2; exit 1; }

current="$HEFAISTOS_CONFIG_DIR/config.json"
work=$(mktemp -d)
trap 'rm -rf "$work"; docker rmi -f hefaistos:configure >/dev/null 2>&1 || true' EXIT

echo "preparing the editor (first run builds the image, later runs use the cache)"
docker build -q -t hefaistos:configure "$root" >/dev/null
docker run -it --rm -v "$HEFAISTOS_CONFIG_DIR:/config:ro" -v "$work:/out" hefaistos:configure configure

[ -f "$work/config.json" ] || exit 0
if [ -f "$current" ] && cmp -s "$current" "$work/config.json"; then echo "no changes"; exit 0; fi
diff -u "$( [ -f "$current" ] && echo "$current" || echo /dev/null )" "$work/config.json" || true
printf 'Install this config and restart hefaistos on %s? [y/N] ' "$QNAP_TARGET"
read -r answer
case "$answer" in y|Y) ;; *) echo "not installed"; exit 0 ;; esac
cp "$work/config.json" "$current"
exec "$root/scripts/qnap-remote.exp" "$QNAP_TARGET" \
  "cd $REMOTE_DIR && docker compose restart && sleep 4 && docker compose logs --tail 4"
