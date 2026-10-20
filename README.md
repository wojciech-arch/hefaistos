# hefaistos

Always-visible Spotify Connect targets for fixed groups of Denon HEOS speakers. Each target, for example **All** or **Downstairs**, is a set of speakers you define. Picking one in any Spotify app on your network makes hefaistos group those speakers. The group appears in Spotify a few seconds later, and you tap it to play there. Audio plays natively on HEOS; hefaistos only does the grouping.

Without hefaistos you have to build the group in the HEOS app before Spotify can see it, and a speaker inside a group disappears from Spotify. hefaistos replaces the HEOS app step for everyone on the network. Nobody needs a Spotify developer app, an account login or any setup beyond joining the Wi-Fi.

## How it works

```text
Spotify app ──picks "All"──▶ librespot endpoint "All" (ZeroConf, never plays audio)
                                  │ onevent: loading / playing
                                  ▼
                        hefaistos hook ──▶ HEOS CLI: stop busy speakers, set_group(leader, members)
                                  ▼
Spotify app ──taps the HEOS group (e.g. "Living + Den + Kids")──▶ plays natively on HEOS
```

- Picking a target takes over its speakers: anything playing on them (e.g. AirPlay) is stopped first.
- Only groups whose composition matches a configured target are changed. A group containing any other speaker is refused.
- Any failure dissolves the half-built group.
- Pausing keeps the group. To play on a single speaker again, AirPlay to it: HEOS dissolves the group itself.

## Limits

- Two taps: the target, then the HEOS group. Until the second tap Spotify plays silently on the target endpoint.
- Spotify shows the group under its HEOS name (e.g. `Living + Den`), not the target name.
- While a group exists, its speakers are hidden in Spotify. Apps without AirPlay (Android, Windows) cannot pick them individually until the group is gone.
- Targets that share speakers cannot play at the same time; picking one takes the speakers from the other.
- Needs Linux Docker with `network_mode: host` on the same LAN as the speakers. Docker Desktop / OrbStack on macOS do not pass mDNS to the LAN.

## Setup

1. Make a config folder outside the repo with `config.json`, copied from [config.example.json](config.example.json). It holds one HEOS speaker's IP and your targets (see [Targets](#targets)).
2. Point compose at it, in `.env` next to `compose.yaml`:

   ```text
   HEFAISTOS_CONFIG_DIR=/path/to/config
   ```

3. Build, then list your HEOS player ids for `config.json`:

   ```bash
   docker compose build
   ```

   ```bash
   docker compose run --rm cli status
   ```

4. Start the endpoints:

   ```bash
   docker compose up -d
   ```

Switch log: `docker compose exec all cat /tmp/hook.log`.

Other CLI commands: `ungroup`, `group <target>`.

## Targets

A target is an entry in `config.json` plus one service in `compose.yaml`. The repo ships two as an example: `all` (three speakers) and `no-kid` (two of them). Rename them, delete them or add more.

`config.json`: the key is the target id. Get player ids from `docker compose run --rm cli status`:

```json
"downstairs": { "leader": 1001, "members": [1002] }
```

`compose.yaml`: `--name` is what Spotify shows.

```yaml
  downstairs:
    <<: *hefaistos
    restart: unless-stopped
    environment:
      HEFAISTOS_TARGET: downstairs
    command: ["--name", "Downstairs"]
```

Choosing the leader: give targets that overlap the same leader, so switching between them reshapes the existing group instead of rebuilding it.

## Tests

```bash
docker build --target test .
```

## Building for a NAS

Building librespot on a small NAS CPU is slow. Build on another machine and copy the image over:

```bash
docker buildx build --platform linux/amd64 -t hefaistos:latest --load . && docker save hefaistos:latest | gzip -1 > hefaistos.tar.gz
```

On the NAS, run `docker load -i hefaistos.tar.gz`, then follow steps 1–4 above, skipping the build.

### Deploying to a QNAP

[scripts/deploy-qnap.sh](scripts/deploy-qnap.sh) does the whole round trip from a Mac or Linux machine that has the QNAP share mounted. It builds the amd64 image and runs the tests, copies the image and `compose.yaml` to the share, then logs in over SSH. There it answers QNAP's console menu (Q, then Y), loads the image and restarts the endpoints. It asks for the password once and never stores it.

```bash
QNAP_TARGET=admin@<nas-ip> LOCAL_DIR=/Volumes/<share>/hefaistos/deploy REMOTE_DIR=/share/<share>/hefaistos/deploy ./scripts/deploy-qnap.sh
```

- The deploy folder needs a `.env` with `HEFAISTOS_CONFIG_DIR=<QNAP path of the folder with config.json>`.
- Use the NAS's IP address, not its `.local` name. With Container Station installed, the `.local` name also resolves to internal bridge addresses, and SSH stalls on those.
- Requires `expect`, which ships with macOS.

## License

MIT. Uses [librespot](https://github.com/librespot-org/librespot) (MIT) and [pyheos](https://github.com/andrewsayre/pyheos) (Apache-2.0).
