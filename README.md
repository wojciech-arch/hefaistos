# hefaistos

Two always-visible Spotify Connect targets, **All** and **No Kid**, for Denon HEOS speakers. Picking one in any Spotify app on your network groups the right HEOS speakers and moves playback to that group in 2–4 seconds. Audio plays natively on HEOS; hefaistos only does the switching.

## How it works

```text
Spotify app ──picks "All"──▶ librespot endpoint "All" (ZeroConf, never plays audio)
                                  │ onevent: loading / playing
                                  ▼
                        hefaistos hook ──▶ HEOS CLI: stop busy speakers, set_group(leader, members)
                                       └─▶ Spotify Web API: transfer playback to the group
```

- A HEOS group appears in Spotify under the leader's device id, so the transfer target is known in advance.
- Reshaping a playing group (All ↔ No Kid) does not interrupt playback; the track position is kept.
- Picking a target takes over its speakers: anything playing on them (e.g. AirPlay) is stopped first.
- Only groups whose composition matches a configured target are changed. A group containing any other speaker is refused.
- Any failure dissolves the half-built group and pauses Spotify; nothing is left "playing" silently.
- Pausing keeps the group. To play on a single speaker again, AirPlay to it: HEOS dissolves the group itself.

## Limits

- The transfer uses the Spotify token of the account that ran `login`, so it works when that account is playing. A Spotify Development Mode app needs a Premium owner and allows up to 5 users.
- While a group plays, its speakers are hidden in Spotify. Apps without AirPlay (Android, Windows) cannot pick them individually until the group is gone.
- After the switch Spotify shows the HEOS group name (e.g. `Living + Den`), not `All`.
- Needs Linux Docker with `network_mode: host` on the same LAN as the speakers. Docker Desktop / OrbStack on macOS do not pass mDNS to the LAN.

## Setup

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard): Web API, redirect URI `http://127.0.0.1:8888/callback`.
2. Make a secrets folder outside the repo with:
   - `.env`:

     ```text
     SPOTIFY_CLIENT_ID=...
     SPOTIFY_SECRET=...
     ```

   - `config.json`, copied from [config.example.json](config.example.json): one HEOS speaker's IP and the targets as player ids (`leader` + `members`).
3. Point compose at it, in `.env` next to `compose.yaml`:

   ```text
   HEFAISTOS_SECRETS=/path/to/secrets
   ```

4. Build, then list your HEOS player ids for `config.json`:

   ```bash
   docker compose build
   ```

   ```bash
   docker compose run --rm cli status
   ```

5. Log in to Spotify once. This needs a browser on the same machine, because the redirect goes to `127.0.0.1:8888`. It stores `spotify_token.json` in the secrets folder:

   ```bash
   docker compose run --rm cli login
   ```

6. Start both endpoints:

   ```bash
   docker compose up -d all no-kid
   ```

Switch log: `docker compose exec all cat /tmp/hook.log`.

Other CLI commands: `ungroup`, `group <target>`, `devices`, `handoff <target>`.

## Tests

```bash
docker build --target test .
```

## Building for a NAS

Building librespot on a small NAS CPU is slow. Build on another machine and copy the image over:

```bash
docker buildx build --platform linux/amd64 -t hefaistos:latest --load . && docker save hefaistos:latest | gzip -1 > hefaistos.tar.gz
```

On the NAS, run `docker load -i hefaistos.tar.gz`, then follow steps 3–6 above, skipping the build.

### Deploying to a QNAP

[scripts/deploy-qnap.sh](scripts/deploy-qnap.sh) does the whole round trip from a Mac or Linux machine that has the QNAP share mounted. It builds the amd64 image and runs the tests, copies the image and `compose.yaml` to the share, then logs in over SSH. There it answers QNAP's console menu (Q, then Y), loads the image and restarts both endpoints. It asks for the password once and never stores it.

```bash
QNAP_TARGET=admin@<nas-ip> LOCAL_DIR=/Volumes/<share>/hefaistos/deploy REMOTE_DIR=/share/<share>/hefaistos/deploy ./scripts/deploy-qnap.sh
```

- The deploy folder needs a `.env` with `HEFAISTOS_SECRETS=<QNAP path of the secrets folder>`.
- Use the NAS's IP address, not its `.local` name. With Container Station installed, the `.local` name also resolves to internal bridge addresses, and SSH stalls on those.
- Requires `expect`, which ships with macOS.

## License

MIT. Uses [librespot](https://github.com/librespot-org/librespot) (MIT) and [pyheos](https://github.com/andrewsayre/pyheos) (Apache-2.0).
