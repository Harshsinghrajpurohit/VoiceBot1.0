"""Desktop OAuth for Google Calendar. PKCE plus a loopback redirect."""

import base64
import hashlib
import html
import http.server
import json
import os
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


def load_client(client_json_path: str) -> tuple[str, str]:
    """Client id and secret from a Desktop-app JSON file."""
    with open(client_json_path, encoding="utf-8") as handle:
        data = json.load(handle)
    installed = data.get("installed") or {}
    client_id = installed.get("client_id", "")
    secret = installed.get("client_secret", "")
    if not client_id:
        raise ValueError("The client JSON has no installed client_id.")
    return client_id, secret


def _challenge() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _auth_url(client_id: str, challenge: str, port: int) -> str:
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": f"http://127.0.0.1:{port}",
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTH_URL}?{params}"


def _wait_for_code(port: int, timeout: float = 180.0) -> str:
    """Serve one loopback request and return the authorization code."""
    codes: list[str] = []
    errors: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            if params.get("code"):
                codes.append(params["code"][0])
            else:
                errors.append(params.get("error", ["denied"])[0])
            body = b"<html><body>You can close this tab.</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = timeout
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout + 5)
    server.server_close()
    if codes:
        return codes[0]
    raise ValueError(html.escape(errors[0] if errors else "sign-in timed out"))


def _post_token(payload: dict) -> dict:
    body = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(
        TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def sign_in(client_json_path: str, token_path: str) -> dict:
    """Browser sign-in once. Saves the refresh token, returns the token set."""
    client_id, secret = load_client(client_json_path)
    verifier, challenge = _challenge()
    server = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
    port = server.server_address[1]
    server.server_close()
    url = _auth_url(client_id, challenge, port)
    print("Opening the browser for Google sign-in.")
    webbrowser.open(url)
    code = _wait_for_code(port)
    tokens = _post_token(
        {
            "client_id": client_id,
            "client_secret": secret,
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": f"http://127.0.0.1:{port}",
        }
    )
    if not tokens.get("refresh_token"):
        raise ValueError("Google did not return a refresh token.")
    folder = os.path.dirname(token_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as handle:
        json.dump(
            {"refresh_token": tokens["refresh_token"], "scope": SCOPE}, handle
        )
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass
    return tokens


def load_refresh_token(token_path: str) -> str:
    try:
        with open(token_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ""
    token = data.get("refresh_token") if isinstance(data, dict) else ""
    return token if isinstance(token, str) else ""


def refresh_access_token(client_json_path: str, refresh_token: str) -> str:
    """One fresh access token. Empty when the refresh fails."""
    try:
        client_id, secret = load_client(client_json_path)
        tokens = _post_token(
            {
                "client_id": client_id,
                "client_secret": secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        )
    except (OSError, ValueError):
        return ""
    token = tokens.get("access_token", "")
    return token if isinstance(token, str) else ""
