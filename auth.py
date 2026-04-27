"""
Token management for Business France Azure B2C.

Flow:
  1. First run: `python login.py` → opens browser, user logs in, tokens saved to token_cache.json
  2. Subsequent runs: access token refreshed automatically from stored refresh_token
  3. Re-login needed only when refresh token expires (~90 days of inactivity)
"""

import json
import logging
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Azure B2C constants extracted from the site's JS bundle
_B2C_BASE = "https://france365B2C.b2clogin.com/france365B2C.onmicrosoft.com"
_POLICY = "B2C_1A_SIGNUP_SIGNIN"
_CLIENT_ID = "cbba759f-45bc-4c21-bd77-533388735d6a"
_SCOPE = " ".join([
    "openid",
    "profile",
    "offline_access",
    "https://france365B2C.onmicrosoft.com/f86b75cc-7549-4e7b-9f20-c41117f94807/access_as_user",
])
TOKEN_ENDPOINT = f"{_B2C_BASE}/{_POLICY}/oauth2/v2.0/token"
AUTH_ENDPOINT = f"{_B2C_BASE}/{_POLICY}/oauth2/v2.0/authorize"
REDIRECT_URI = "https://mon-vie-via.businessfrance.fr"

TOKEN_CACHE_FILE = Path("token_cache.json")


def _load_cache() -> dict:
    if TOKEN_CACHE_FILE.exists():
        try:
            return json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not read token cache: {e}")
    return {}


def _save_cache(data: dict) -> None:
    TOKEN_CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_expired(cache: dict, buffer_seconds: int = 60) -> bool:
    expires_at = cache.get("expires_at", 0)
    return time.time() >= expires_at - buffer_seconds


def _refresh(refresh_token: str) -> dict:
    """Exchange a refresh token for a new token set."""
    resp = requests.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "refresh_token",
            "client_id": _CLIENT_ID,
            "refresh_token": refresh_token,
            "scope": _SCOPE,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def get_access_token() -> str:
    """
    Return a valid access token, refreshing from cache if needed.
    Raises RuntimeError if no valid credentials are stored (run login.py first).
    """
    cache = _load_cache()

    if not cache.get("access_token"):
        raise RuntimeError(
            "No token found. Run `python login.py` first to authenticate."
        )

    if not _is_expired(cache):
        return cache["access_token"]

    refresh_token = cache.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(
            "Access token expired and no refresh token found. "
            "Run `python login.py` again."
        )

    logger.info("Access token expired — refreshing…")
    try:
        tokens = _refresh(refresh_token)
    except requests.HTTPError as e:
        raise RuntimeError(
            f"Token refresh failed ({e}). Run `python login.py` again."
        ) from e

    _store_tokens(tokens)
    logger.info("Token refreshed successfully")
    return tokens["access_token"]


def _store_tokens(tokens: dict) -> None:
    """Persist tokens with computed expiry timestamp."""
    expires_in = int(tokens.get("expires_in", 3600))
    cache = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token") or _load_cache().get("refresh_token"),
        "expires_at": time.time() + expires_in,
        "token_type": tokens.get("token_type", "Bearer"),
    }
    _save_cache(cache)


def store_tokens_from_login(tokens: dict) -> None:
    """Called by login.py after successful interactive auth."""
    _store_tokens(tokens)
    logger.info("Tokens stored successfully")
