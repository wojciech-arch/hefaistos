#!/bin/sh
# Build the amd64 image, copy it with compose.yaml to the QNAP share, then load and restart it there.
#
# Set these in .env next to compose.yaml, or in the environment:
# QNAP_TARGET  ssh target, e.g. admin@192.168.0.10
# LOCAL_DIR    the deploy folder as mounted on this machine, e.g. /Volumes/share/hefaistos/deploy
# REMOTE_DIR   the same folder as seen on the QNAP, e.g. /share/share/hefaistos/deploy
# The deploy folder must already hold a .env with HEFAISTOS_CONFIG_DIR=<QNAP path of the folder with config.json>.
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
. "$root/scripts/env.sh"
load_env "$root/.env"
: "${QNAP_TARGET:?set QNAP_TARGET, e.g. admin@nas.local}"
: "${LOCAL_DIR:?set LOCAL_DIR to the deploy folder as mounted locally}"
: "${REMOTE_DIR:?set REMOTE_DIR to the deploy folder path on the QNAP}"

grep -q '^HEFAISTOS_CONFIG_DIR=' "$LOCAL_DIR/.env" 2>/dev/null || { echo "$LOCAL_DIR/.env must set HEFAISTOS_CONFIG_DIR=<QNAP path of the folder with config.json>" >&2; exit 1; }

echo "building hefaistos:latest for linux/amd64"
docker buildx build --platform linux/amd64 --target test "$root"
docker buildx build -q --platform linux/amd64 -t hefaistos:latest --load "$root"
echo "copying image and compose.yaml to $LOCAL_DIR"
docker save hefaistos:latest | gzip -1 > "$LOCAL_DIR/hefaistos.tar.gz"
cp "$root/compose.yaml" "$LOCAL_DIR/compose.yaml"

exec "$root/scripts/qnap-remote.exp" "$QNAP_TARGET" \
  "cd $REMOTE_DIR && docker load -i hefaistos.tar.gz && docker compose up -d --remove-orphans && sleep 5 && docker compose ps && docker compose logs --tail 3"
