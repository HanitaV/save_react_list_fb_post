"""Create an authorized Facebook browser session through a manual login."""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "services" / "api"))
os.chdir(ROOT)


def main() -> None:
    from app.browser_session import filter_facebook_state, proxy_config
    from cloakbrowser import launch

    output = ROOT / "secrets" / "facebook-state.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    browser = launch(
        headless=False,
        proxy=proxy_config(),
        stealth_args=False,
        geoip=False,
        humanize=False,
    )
    try:
        context = browser.new_context()
        try:
            page = context.new_page()
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            input(
                "Log in manually in the browser, then press Enter here to save the session... "
            )
            path = urlsplit(page.url).path.lower()
            if any(
                segment in path for segment in ("/login", "/checkpoint", "/recover")
            ):
                raise RuntimeError("Finish the login or checkpoint flow before saving")
            state = filter_facebook_state(context.storage_state())
            temporary = output.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(state), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(output)
            print(f"Saved session to {output}")
        finally:
            context.close()
    finally:
        browser.close()


if __name__ == "__main__":
    main()
