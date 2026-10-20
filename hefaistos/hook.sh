#!/bin/sh
# librespot --onevent target. Runs the handoff detached so librespot's event loop is never blocked.
case "$PLAYER_EVENT" in
  loading|playing) cd /app && nohup python -m hefaistos hook "$HEFAISTOS_TARGET" >>/tmp/hook.log 2>&1 & ;;
esac
