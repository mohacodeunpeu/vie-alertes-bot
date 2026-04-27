"""
One-time interactive login for the VIE scraper bot.

Run this once before starting main.py:
    python login.py

It opens a Chromium browser → you log in on the Business France site →
the script captures the access + refresh tokens → saves them to token_cache.json.
After that, main.py refreshes the access token automatically (valid ~90 days).
"""

import json
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _try_extract_from_local_storage(page) -> dict | None:
    """Pull token from the site's localStorage (stored by nuxt-auth)."""
    try:
        raw = page.evaluate("() => JSON.stringify(window.localStorage)")
        store = json.loads(raw or "{}")
        for key, value in store.items():
            if "auth" in key.lower() or "token" in key.lower():
                try:
                    parsed = json.loads(value) if isinstance(value, str) else value
                    if isinstance(parsed, dict) and parsed.get("access_token"):
                        return parsed
                    if isinstance(value, str) and value.startswith("ey"):
                        return {"access_token": value}
                except Exception:
                    pass
        # Also try nuxt-auth specific key
        for prefix in ["auth.", "_auth.", "nuxt-"]:
            token = store.get(f"{prefix}access_token") or store.get(f"{prefix}token")
            refresh = store.get(f"{prefix}refresh_token")
            if token:
                return {"access_token": token, "refresh_token": refresh, "expires_in": 3600}
    except Exception as e:
        logger.debug(f"localStorage extraction error: {e}")
    return None


def _try_extract_from_cookie(context) -> str | None:
    """Extract access token stored as cookie."""
    try:
        cookies = context.cookies()
        for c in cookies:
            if "token" in c["name"].lower() and c["value"].startswith("ey"):
                return c["value"]
    except Exception:
        pass
    return None


def run_login() -> None:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print(
            "\n[ERROR] Playwright is not installed.\n"
            "Run: pip install playwright && python -m playwright install chromium\n"
        )
        sys.exit(1)

    import auth

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context()
        page = context.new_page()

        tokens_found: dict | None = None
        captured_requests: list[dict] = []

        # Intercept API calls to capture the Bearer token in use
        def on_request(request):
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer ey") and "offres" in request.url:
                token = auth_header.removeprefix("Bearer ")
                captured_requests.append({"access_token": token, "expires_in": 3600})

        page.on("request", on_request)

        logger.info("Opening Business France — please log in in the browser window…")
        page.goto("https://mon-vie-via.businessfrance.fr/offres", timeout=30_000)

        # Wait for user to complete login (up to 3 minutes)
        deadline = time.time() + 180
        while time.time() < deadline:
            url = page.url
            # Check for redirect after successful login
            if "mon-vie-via.businessfrance.fr" in url and "#" not in url:
                # Try to extract tokens
                tokens_found = _try_extract_from_local_storage(page)
                if tokens_found:
                    logger.info("Token captured from localStorage")
                    break
                if captured_requests:
                    tokens_found = captured_requests[-1]
                    logger.info("Token captured from intercepted API request")
                    break

            # Poll for token every 2 seconds
            time.sleep(2)
            if not tokens_found:
                tokens_found = _try_extract_from_local_storage(page)
            if not tokens_found and captured_requests:
                tokens_found = captured_requests[-1]
            if tokens_found:
                break

        browser.close()

    if not tokens_found or not tokens_found.get("access_token"):
        print(
            "\n[ERROR] Could not capture token.\n"
            "Make sure you logged in fully on the Business France site.\n"
        )
        sys.exit(1)

    # Add refresh token from localStorage if not in captured token
    if not tokens_found.get("refresh_token"):
        logger.warning(
            "No refresh_token captured — you may need to re-run login.py "
            "when the access token expires (typically in 1 hour)."
        )

    auth.store_tokens_from_login(tokens_found)
    print("\n✅ Login successful — tokens saved to token_cache.json")
    print("You can now run: python main.py")


if __name__ == "__main__":
    run_login()
