# hefaistos

Always-visible Spotify Connect targets for fixed groups of Denon HEOS speakers. Each target, for example **All** or **Downstairs**, is a set of speakers you define. Picking one in any Spotify app on your network makes hefaistos group those speakers. The group appears in Spotify a few seconds later, and you tap it to play there. Audio plays natively on HEOS; hefaistos only does the grouping.

Without hefaistos you have to build the group in the HEOS app before Spotify can see it, and a speaker inside a group disappears from Spotify. The HEOS app's Group Presets make that one tap, but only inside the HEOS app. hefaistos puts the same tap in Spotify for everyone on the network. Nobody needs a Spotify developer app, an account login or any setup beyond joining the Wi-Fi.

## Using it

1. In Spotify, pick a target such as **All**.
2. The target disappears straight away and playback pauses; a few seconds later its HEOS group appears (e.g. **Living + Den + Kids**). Tap the group and press play.
3. To play on one speaker only, AirPlay to it. HEOS dissolves the group, and the targets come back.

## How it works

```text
Spotify app ──picks "All"──▶ librespot endpoint "All" (ZeroConf, never plays audio)
                                  │ onevent: loading / playing
                                  ▼
                        hefaistos hook ──▶ HEOS CLI: stop busy speakers, set_group(leader, members)
                                  ▼
hefaistos serve (polls HEOS groups every 2 s) ──▶ stops the "All" endpoint while its group exists
                                  ▼
Spotify app ──taps the HEOS group (e.g. "Living + Den + Kids")──▶ plays natively on HEOS
```

- Picking a target takes over its speakers: anything playing on them (AirPlay, a group made in the HEOS app) is stopped, and any group holding them is dissolved. The target's group is then built fresh, so HEOS names it after its speakers.
- Groups that share no speaker with the target are never touched.
- A target is listed only while its group does not exist; the group itself takes its place. Switching to another target, or AirPlay to one of its speakers (which dissolves the group), brings it back. If HEOS cannot be reached, every target is listed.
- Each target listens on a fixed ZeroConf port, 50100 upwards in `config.json` order (`HEFAISTOS_ZEROCONF_PORT_BASE` changes the start). Fixed ports let Spotify apps find a restarted endpoint at its cached address.
- Any failure dissolves the half-built group.
- Pausing keeps the group. To play on a single speaker again, AirPlay to it: HEOS dissolves the group itself.

## Limits

- Two taps: the target, then the HEOS group. Once the group is formed the target disappears from Spotify and playback pauses; tap the group and press play.
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
   docker compose run --rm hefaistos status
   ```

4. Start the endpoints:

   ```bash
   docker compose up -d
   ```

Switch log: `docker compose exec hefaistos cat /tmp/hook.log`.

Other CLI commands: `ungroup`, `group <target>`.

## Targets

A target is one entry in `config.json`. One container serves all of them; after editing by hand, restart with `docker compose restart`, or use [configure.sh](#changing-targets-on-a-nas), which edits and restarts for you. The example ships two: **All** (three speakers) and **No Kid** (two of them). Rename them, delete them or add more.

```json
"targets": {
  "all":        { "name": "All",        "leader": 1001, "members": [1002, 1003] },
  "no-kid":     { "name": "No Kid",     "leader": 1001, "members": [1002] },
  "quiet-room": { "name": "Quiet Room", "leader": 1002, "members": [1003] }
}
```

- `name` is what Spotify shows, and must be unique. Spotify keeps a device id per name, so renaming makes a new device.
- Player ids come from `docker compose run --rm hefaistos status`.
- The leader is the speaker Spotify streams to; it relays the audio to the members. Pick the one with the best network connection, ideally the one nearest the router or wired. In `configure.sh` it is the first speaker you type.
- HEOS player ids identify speakers, not names: after renaming or swapping speakers in the HEOS app, pick the targets' speakers again.

### Strategy: rebuild or switch

Each target has a `strategy`:

- `rebuild` (default): hefaistos dissolves any group holding the target's speakers and builds the target with HEOS's documented `set_group`. Takes 3–4 s, and HEOS names the group after its speakers.
- `switch`: HEOS applies one of its own Group Presets, given by `preset` (ids from `docker compose run --rm hefaistos presets`). The group keeps the preset's name.

```json
"no-kid": { "name": "No Kid", "leader": 1001, "members": [1002], "strategy": "switch", "preset": "ec496221-..." }
```

Caveats for `switch`, seen on HEOS firmware 3.139:

- It uses undocumented HEOS commands (`get_group_presets`, `apply_group_preset`), which an update may change.
- Adding speakers takes about 1 s, removing one about 20 s.
- Presets live on one speaker; set `heos_host` to it. That speaker only picks up presets created or deleted in the HEOS app after it restarts.
- `leader` and `members` must match the preset's speakers; hefaistos uses them to tell when the group is ready and when to hide the target.

### Changing targets on a NAS

[scripts/configure.sh](scripts/configure.sh) edits the targets in a terminal menu, shows the `config.json` diff, and after you confirm, installs it on the NAS and restarts hefaistos there. It reads `HEFAISTOS_CONFIG_DIR` (the config folder as mounted on your machine), `QNAP_TARGET` and `REMOTE_DIR` from `.env` next to `compose.yaml`:

```bash
./scripts/configure.sh
```

The editor runs in the hefaistos image on your machine, so it needs Docker there and network access to a HEOS speaker. It validates targets before saving: at least 2 speakers, unique names, and no two targets with the same speakers. The restart uses the same SSH login as [Deploying to a QNAP](#deploying-to-a-qnap).

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

The three variables can also live in `.env` next to `compose.yaml`; then `./scripts/deploy-qnap.sh` alone is enough.

- The deploy folder needs a `.env` with `HEFAISTOS_CONFIG_DIR=<QNAP path of the folder with config.json>`.
- Use the NAS's IP address, not its `.local` name. With Container Station installed, the `.local` name also resolves to internal bridge addresses, and SSH stalls on those.
- Requires `expect`, which ships with macOS.

## License

MIT. Uses [librespot](https://github.com/librespot-org/librespot) (MIT) and [pyheos](https://github.com/andrewsayre/pyheos) (Apache-2.0).
