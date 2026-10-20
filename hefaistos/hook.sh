#!/bin/sh
# librespot --onevent target. Runs the grouping detached so librespot's event loop is never blocked.
# librespot spawns this script directly, so $PPID is the endpoint the hook may release afterwards.
case "$PLAYER_EVENT" in
  loading|playing) cd /app && HEFAISTOS_ENDPOINT_PID="$PPID" nohup python -m hefaistos hook "$HEFAISTOS_TARGET" >>/tmp/hook.log 2>&1 & ;;
esac
