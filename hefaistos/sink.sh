#!/bin/sh
# librespot subprocess sink: drains S16/44.1 kHz/stereo PCM at roughly real time (176400 B/s) and discards it.
# A /dev/null pipe sink is consumed instantly, so librespot "finishes" each track in ~1 s and skips through the queue.
while :; do dd bs=17640 count=1 of=/dev/null 2>/dev/null || exit 0; sleep 0.1; done
