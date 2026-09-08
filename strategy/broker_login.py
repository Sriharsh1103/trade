#!/usr/bin/env python3
"""Automated login for the browser-automation trading path.

Reads config/credentials.yaml and logs into whichever practice-trading web
terminal actually has credentials filled in — the MetaTrader web terminal
(web.metatrader.app, the account referenced by config/config.yaml's
broker.account_id) or the Exness web terminal (my.exness.com), preferring
MetaTrader since that's the currently active practice account. If neither
section has a login+password, or the login attempt fails (e.g. the vendor
changed their login form), callers should fall back to asking for manual
login in the already-open browser — this module never blocks on that.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("broker_login")

CREDENTIALS_FILE = Path(__file__).resolve().parent.parent / "config" / "credentials.yaml"

METATRADER_URL = "https://web.metatrader.app/terminal?lang=en"
EXNESS_URL = "https://my.exness.com/webtrading/"


def load_credentials() -> dict[str, Any]:
    if not CREDENTIALS_FILE.exists():
        return {}
    try:
        import yaml
    except ImportError:
        log.warning("PyYAML not installed — cannot read credentials.yaml (pip install pyyaml)")
        return {}
    return yaml.safe_load(CREDENTIALS_FILE.read_text()) or {}


def target_platform() -> tuple[str, str, str, str] | None:
    """Return (platform, url, login, password) for whichever section is filled in.

    Prefers metatrader: (the account config/config.yaml is actually pointed
    at today), falls back to exness:.
    """
    creds = load_credentials()
    mt = creds.get("metatrader") or {}
    if mt.get("login") and mt.get("password"):
        return "metatrader", METATRADER_URL, str(mt["login"]), str(mt["password"])
    ex = creds.get("exness") or {}
    if ex.get("login") and ex.get("password"):
        return "exness", EXNESS_URL, str(ex["login"]), str(ex["password"])
    return None


def _looks_logged_in(page) -> bool:
    try:
        return (
            page.get_by_role("button", name="Buy").count() > 0
            or page.get_by_role("button", name="Sell").count() > 0
        )
    except Exception:
        return False


def ensure_logged_in(page, timeout_s: float = 30.0) -> bool:
    """Best-effort automated login on an already-open terminal page.

    Returns True once the terminal shows Buy/Sell controls (logged in).
    Returns False if there are no usable credentials or the login form
    couldn't be filled — the caller should then prompt for manual login
    rather than treat this as fatal, since login-form selectors are
    inherently brittle against a third-party site.
    """
    target = target_platform()
    if target is None:
        log.warning("No usable credentials in config/credentials.yaml — log in manually")
        return False
    platform, url, login, password = target

    if url.split("?")[0] not in page.url:
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(2)

    if _looks_logged_in(page):
        return True

    try:
        login_field = page.get_by_placeholder("Login").first
        if login_field.count() == 0:
            login_field = page.locator("input[name='login'], input[type='text']").first
        login_field.fill(login, timeout=5000)

        password_field = page.get_by_placeholder("Password").first
        if password_field.count() == 0:
            password_field = page.locator("input[type='password']").first
        password_field.fill(password, timeout=5000)

        submit = page.get_by_role("button", name="Log in")
        if submit.count() == 0:
            submit = page.get_by_role("button", name="Login")
        if submit.count() == 0:
            submit = page.locator("button[type='submit']").first
        submit.first.click(timeout=5000)
    except Exception as exc:
        log.warning("Automated login form-fill failed (%s) — log in manually in the opened browser", exc)
        return False

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _looks_logged_in(page):
            log.info("Logged into %s as %s", platform, login)
            return True
        time.sleep(1)

    log.warning("Login submitted but terminal didn't confirm within %.0fs — check the browser", timeout_s)
    return False
