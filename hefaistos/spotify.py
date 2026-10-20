"""Spotify Web API: Authorization Code login, token refresh, devices, transfer.

Secrets live on the QNAP share mounted at /secrets: `.env` (client id/secret, written by
Caesar) and `spotify_token.json` (refresh token, written here). Neither is ever logged.
"""

import base64
import http.server
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SECRETS = Path(os.environ.get("HEFAISTOS_SECRETS", "/secrets"))
TOKEN_FILE = SECRETS / "spotify_token.json"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-playback-state user-modify-playback-state"
API = "https://api.spotify.com/v1"


@dataclass(frozen=True)
class Client:
    client_id: str
    client_secret: str


def load_client() -> Client:
    env_path = SECRETS / ".env"
    if not env_path.exists():
        raise SystemExit(f"{env_path} not found; mount the QNAP share with .env at {SECRETS}")
    env: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    cid = env.get("SPOTIFY_CLIENT_ID")
    secret = env.get("SPOTIFY_SECRET") or env.get("SPOTIFI_SECRET") or env.get("SPOTIFY_CLIENT_SECRET")
    if not cid or not secret:
        raise SystemExit(f"{env_path} must define SPOTIFY_CLIENT_ID and SPOTIFY_SECRET")
    return Client(cid, secret)


def _token_request(client: Client, form: dict[str, str]) -> dict[str, object]:
    basic = base64.b64encode(f"{client.client_id}:{client.client_secret}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=urllib.parse.urlencode(form).encode(),
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Spotify token endpoint {e.code}: {e.read().decode()[:300]}; "
                         "check client id/secret in .env and the redirect URI in the Spotify dashboard") from e


def login(client: Client) -> None:
    state = secrets.token_urlsafe(16)
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {"client_id": client.client_id, "response_type": "code", "redirect_uri": REDIRECT_URI,
         "scope": SCOPES, "state": state}
    )
    print(f"Open in your browser and approve:\n{url}\n", flush=True)
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                self.send_error(400, "state mismatch")
                return
            result.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"hefaistos: login received, you can close this tab.")

        def log_message(self, *_: object) -> None:
            pass

    server = http.server.HTTPServer(("0.0.0.0", 8888), Handler)
    while "code" not in result and "error" not in result:
        server.handle_request()
    if "error" in result:
        raise SystemExit(f"Spotify login refused: {result['error']}")
    tok = _token_request(client, {"grant_type": "authorization_code", "code": result["code"],
                                  "redirect_uri": REDIRECT_URI})
    TOKEN_FILE.write_text(json.dumps({"refresh_token": tok["refresh_token"], "scope": tok.get("scope")}))
    TOKEN_FILE.chmod(0o600)
    print(f"refresh token saved to {TOKEN_FILE} (scope: {tok.get('scope')})", flush=True)


def _parse(raw: bytes) -> dict[str, object]:
    # Player endpoints sometimes answer 200 with a non-JSON body instead of 204.
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"raw": raw[:200].decode(errors="replace")}
    return body if isinstance(body, dict) else {"value": body}


class Api:
    def __init__(self, client: Client) -> None:
        if not TOKEN_FILE.exists():
            raise SystemExit("no Spotify token; run `login` first")
        saved = json.loads(TOKEN_FILE.read_text())
        tok = _token_request(client, {"grant_type": "refresh_token", "refresh_token": saved["refresh_token"]})
        if "refresh_token" in tok:
            TOKEN_FILE.write_text(json.dumps({**saved, "refresh_token": tok["refresh_token"]}))
        self._access = str(tok["access_token"])

    def call(self, method: str, path: str, body: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        req = urllib.request.Request(
            API + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self._access}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, _parse(r.read())
        except urllib.error.HTTPError as e:
            return e.code, _parse(e.read())

    def devices(self) -> list[dict[str, object]]:
        status, body = self.call("GET", "/me/player/devices")
        if status != 200:
            raise RuntimeError(f"GET /me/player/devices -> {status} {body}")
        return list(body.get("devices", []))  # type: ignore[arg-type]

    def player(self) -> dict[str, object]:
        status, body = self.call("GET", "/me/player")
        return body if status == 200 else {}

    def transfer(self, device_id: str) -> tuple[int, dict[str, object]]:
        return self.call("PUT", "/me/player", {"device_ids": [device_id], "play": True})
