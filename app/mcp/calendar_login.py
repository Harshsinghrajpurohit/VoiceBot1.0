"""Sign in to Google Calendar once. Saves a refresh token under data/."""

import sys

from app.config.settings import load_settings
from app.mcp import google_auth


def main() -> int:
    settings = load_settings()
    if not settings.google_client_json.strip():
        print("Set GOOGLE_CALENDAR_CLIENT_JSON in .env first.")
        return 1
    try:
        google_auth.sign_in(
            settings.google_client_json.strip(), "data/google_token.json"
        )
    except (OSError, ValueError) as exc:
        print(f"Google sign-in failed: {exc}")
        return 1
    print("Signed in. The refresh token is saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
