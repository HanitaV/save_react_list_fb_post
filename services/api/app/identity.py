import hashlib
import hmac
import re
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .config import settings


def normalize_identifier(value: str) -> str:
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme and parts.netloc:
        host = parts.hostname.lower() if parts.hostname else ""
        if host not in {
            "facebook.com",
            "www.facebook.com",
            "m.facebook.com",
            "fb.com",
            "www.fb.com",
        }:
            raise ValueError("Only Facebook profile URLs are supported")
        path = parts.path.rstrip("/").lower()
        group_member = re.fullmatch(r"/groups/[^/]+/user/(\d+)", path)
        people_profile = re.fullmatch(r"/people/[^/]+/(\d+)", path)
        if group_member or people_profile:
            return (
                f"facebook:profile.php?id={(group_member or people_profile).group(1)}"
            )
        if path == "/profile.php":
            ids = parse_qs(parts.query).get("id")
            if not ids:
                raise ValueError("Profile URL needs an id")
            return f"facebook:profile.php?id={ids[0]}"
        if not path or path == "/":
            raise ValueError("Profile URL needs a path")
        return f"facebook:{path}"
    if not value:
        raise ValueError("Missing identifier")
    return value.casefold()


def actor_hash(identifier: str, secret: str | None = None) -> str:
    normalized = normalize_identifier(identifier)
    return hmac.new(
        (secret or settings.app_secret).encode(), normalized.encode(), hashlib.sha256
    ).hexdigest()


def canonical_post_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or (parts.hostname or "").lower() not in {
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
        "fb.com",
        "www.fb.com",
    }:
        raise ValueError("Use an HTTPS Facebook post URL")
    return urlunsplit(
        (
            "https",
            (parts.hostname or "").lower(),
            parts.path.rstrip("/"),
            parts.query,
            "",
        )
    )
