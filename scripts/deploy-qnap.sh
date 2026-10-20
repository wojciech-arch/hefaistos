#!/bin/sh
# Build the amd64 image, copy it with compose.yaml to the QNAP share, then load and restart it there.
#
# QNAP_TARGET  ssh target, e.g. admin@nas.local
# LOCAL_DIR    the deploy folder as mounted on this machine, e.g. /Volumes/share/hefaistos/deploy
# REMOTE_DIR   the same folder as seen on the QNAP, e.g. /share/share/hefaistos/deploy
# The deploy folder must already hold a .env with HEFAISTOS_SECRETS=<QNAP path of the secrets folder>.
set -eu

: "${QNAP_TARGET:?set QNAP_TARGET, e.g. admin@nas.local}"
: "${LOCAL_DIR:?set LOCAL_DIR to the deploy folder as mounted locally}"
: "${REMOTE_DIR:?set REMOTE_DIR to the deploy folder path on the QNAP}"

root=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$LOCAL_DIR/.env" ] || { echo "missing $LOCAL_DIR/.env (HEFAISTOS_SECRETS=<QNAP path of secrets folder>)" >&2; exit 1; }

echo "building hefaistos:latest for linux/amd64"
docker buildx build --platform linux/amd64 --target test "$root"
docker buildx build -q --platform linux/amd64 -t hefaistos:latest --load "$root"
echo "copying image and compose.yaml to $LOCAL_DIR"
docker save hefaistos:latest | gzip -1 > "$LOCAL_DIR/hefaistos.tar.gz"
cp "$root/compose.yaml" "$LOCAL_DIR/compose.yaml"

exec "$root/scripts/qnap-remote.exp" "$QNAP_TARGET" \
  "cd $REMOTE_DIR && docker load -i hefaistos.tar.gz && docker compose up -d && sleep 5 && docker compose ps && docker compose logs --tail 3"
