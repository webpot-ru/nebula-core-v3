#!/usr/bin/env python3
"""Issue a YouTube OAuth refresh token for one configured account.

The script intentionally avoids printing refresh tokens. Use
--update-github-secret to write the token directly to GitHub repository secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from google_auth_oauthlib.flow import InstalledAppFlow


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHANNELS_JSON = PROJECT_ROOT / "channels.json"

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"


class TokenIssueError(RuntimeError):
    pass


def load_channel(account_index: int) -> dict[str, Any]:
    channel_id = f"acc{account_index}"
    with CHANNELS_JSON.open("r", encoding="utf-8") as f:
        channels = json.load(f).get("channels", [])
    for channel in channels:
        if channel.get("id") == channel_id:
            return channel
    raise TokenIssueError(f"{CHANNELS_JSON} has no channel with id={channel_id}.")


def client_config(client_id: str, client_secret: str) -> dict[str, Any]:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def issue_refresh_token(
    *,
    client_id: str,
    client_secret: str,
    scopes: list[str],
    port: int,
    open_browser: bool,
) -> str:
    flow = InstalledAppFlow.from_client_config(client_config(client_id, client_secret), scopes=scopes)
    creds = flow.run_local_server(
        host="127.0.0.1",
        port=port,
        open_browser=open_browser,
        authorization_prompt_message=(
            "Open this URL in a browser, log into the correct YouTube channel account, "
            "and approve all requested scopes:\n\n{url}\n\n"
        ),
        success_message="OAuth approval received. You can close this browser tab.",
        access_type="offline",
        prompt="consent",
        include_granted_scopes="false",
    )
    if not creds.refresh_token:
        raise TokenIssueError(
            "Google did not return a refresh token. Re-run with prompt=consent, "
            "make sure the correct Google account was selected, and remove old app consent if needed."
        )
    return str(creds.refresh_token)


def update_github_secret(repo: str, secret_name: str, refresh_token: str) -> None:
    completed = subprocess.run(
        ["gh", "secret", "set", secret_name, "--repo", repo, "--body", refresh_token],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "gh secret set failed").strip()
        raise TokenIssueError(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue a scoped YouTube refresh token for one acc#.")
    parser.add_argument("--account-index", type=int, required=True, choices=range(1, 8))
    parser.add_argument("--repo", default="webpot-ru/nebula-core-v3")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Print the URL instead of opening a browser.")
    parser.add_argument(
        "--include-analytics",
        action="store_true",
        help="Also request yt-analytics.readonly. Not needed for upload/channel mapping.",
    )
    parser.add_argument(
        "--update-github-secret",
        action="store_true",
        help="Write the new refresh token directly to YOUTUBE_REFRESH_TOKEN_ACC# via gh secret set.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise TokenIssueError("Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in the local shell first.")

    channel = load_channel(args.account_index)
    secret_name = f"YOUTUBE_REFRESH_TOKEN_ACC{args.account_index}"
    scopes = list(DEFAULT_SCOPES)
    if args.include_analytics:
        scopes.append(ANALYTICS_SCOPE)

    print(f"Issuing OAuth refresh token for {channel.get('id')} -> {channel.get('name')} ({channel.get('handle')})")
    print("Requested scopes:")
    for scope in scopes:
        print(f"- {scope}")
    print("Important: choose the Google account that owns this exact YouTube channel.")

    refresh_token = issue_refresh_token(
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
        port=args.port,
        open_browser=not args.no_browser,
    )

    if args.update_github_secret:
        update_github_secret(args.repo, secret_name, refresh_token)
        print(f"Updated GitHub secret {secret_name} in {args.repo}.")
    else:
        print(
            f"New refresh token was issued for {secret_name}, but it was not printed. "
            "Re-run with --update-github-secret to store it safely."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TokenIssueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
