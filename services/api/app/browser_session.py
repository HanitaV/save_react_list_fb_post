"""Fixed proxy and operator supplied Facebook session configuration."""

import json
import os
import stat
from pathlib import Path
from urllib.parse import urlsplit

from .config import settings


def proxy_config() -> dict[str, str] | None:
    server = settings.browser_proxy_server
    if not server:
        if settings.browser_proxy_username or settings.browser_proxy_password:
            raise ValueError("Proxy credentials require BROWSER_PROXY_SERVER")
        return None
    parsed = urlsplit(server)
    if (
        parsed.scheme not in {"http", "https", "socks5"}
        or not parsed.hostname
        or parsed.port is None
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "BROWSER_PROXY_SERVER must be an HTTP, HTTPS, or SOCKS5 URL with host and port"
        )
    username = settings.browser_proxy_username
    password = settings.browser_proxy_password
    if bool(username) != bool(password):
        raise ValueError("Set both proxy username and password")
    config = {"server": server}
    if username and password:
        config.update({"username": username, "password": password})
    return config


def _facebook_host(value: str) -> bool:
    host = value.lower().lstrip(".")
    return host in {"facebook.com", "fb.com"} or host.endswith(
        (".facebook.com", ".fb.com")
    )


def filter_facebook_state(state: dict) -> dict:
    cookies = state.get("cookies")
    if not isinstance(cookies, list):
        raise ValueError("Storage state must contain a cookies array")
    selected = [
        cookie
        for cookie in cookies
        if isinstance(cookie, dict) and _facebook_host(str(cookie.get("domain", "")))
    ]
    if not selected:
        raise ValueError("Storage state has no Facebook cookies")
    origins = state.get("origins", [])
    if not isinstance(origins, list):
        raise ValueError("Storage state origins must be an array")
    selected_origins = [
        origin
        for origin in origins
        if isinstance(origin, dict)
        and _facebook_host(urlsplit(str(origin.get("origin", ""))).hostname or "")
    ]
    return {"cookies": selected, "origins": selected_origins}


def storage_state() -> dict | None:
    filename = settings.browser_storage_state_path
    if not filename:
        return None
    path = Path(filename).expanduser().resolve()
    if not path.is_file():
        raise ValueError("Configured browser storage state file is missing")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Browser storage state must be readable only by its owner")
    return filter_facebook_state(json.loads(path.read_text(encoding="utf-8")))
