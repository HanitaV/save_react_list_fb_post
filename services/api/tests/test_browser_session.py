import json
from types import SimpleNamespace

import pytest

from app import tasks
from app.browser_session import filter_facebook_state, proxy_config, storage_state
from app.config import settings


def test_proxy_config_uses_fixed_server_and_separate_credentials(monkeypatch):
    monkeypatch.setattr(settings, "browser_proxy_server", "socks5://proxy.example:1080")
    monkeypatch.setattr(settings, "browser_proxy_username", "operator")
    monkeypatch.setattr(settings, "browser_proxy_password", "secret")
    assert proxy_config() == {
        "server": "socks5://proxy.example:1080",
        "username": "operator",
        "password": "secret",
    }
    monkeypatch.setattr(
        settings, "browser_proxy_server", "http://user:secret@proxy.example:8080"
    )
    with pytest.raises(ValueError):
        proxy_config()
    monkeypatch.setattr(settings, "browser_proxy_server", None)
    with pytest.raises(ValueError):
        proxy_config()


def test_storage_state_filters_other_domains(monkeypatch, tmp_path):
    path = tmp_path / ".test-session.json"
    try:
        path.write_text(
            json.dumps(
                {
                    "cookies": [
                        {
                            "name": "session",
                            "value": "fb-secret",
                            "domain": ".facebook.com",
                            "path": "/",
                        },
                        {
                            "name": "other",
                            "value": "other-secret",
                            "domain": ".example.com",
                            "path": "/",
                        },
                    ],
                    "origins": [
                        {"origin": "https://www.facebook.com", "localStorage": []},
                        {"origin": "https://example.com", "localStorage": []},
                    ],
                }
            )
        )
        path.chmod(0o600)
        monkeypatch.setattr(settings, "browser_storage_state_path", str(path))
        loaded = storage_state()
        assert loaded["cookies"][0]["value"] == "fb-secret"
        assert len(loaded["cookies"]) == 1
        assert len(loaded["origins"]) == 1
        assert "other-secret" not in json.dumps(loaded)
    finally:
        path.unlink(missing_ok=True)


def test_storage_state_rejects_missing_facebook_cookies():
    with pytest.raises(ValueError):
        filter_facebook_state({"cookies": [{"domain": "example.com"}]})


def test_worker_reuses_cloakbrowser_and_loads_state(monkeypatch):
    launched = []
    contexts = []

    class Locator:
        def __init__(self, name):
            self.name = name
            self.first = self

        def count(self):
            return 0 if self.name.startswith("img") else 1

        def is_visible(self):
            return True

        def inner_text(self, timeout=None):
            return "Visible profile" if self.name == "h1" else "Visible public page"

    class Page:
        url = "https://www.facebook.com/example.profile"

        def route(self, pattern, handler):
            pass

        def goto(self, url, **kwargs):
            return SimpleNamespace(status=200)

        def locator(self, name):
            return Locator(name)

        def screenshot(self, **kwargs):
            return b"screenshot"

    class Context:
        def new_page(self):
            return Page()

        def close(self):
            pass

    class Browser:
        def new_context(self, **kwargs):
            contexts.append(kwargs)
            return Context()

        def close(self):
            pass

    def fake_launch(**kwargs):
        launched.append(kwargs)
        return Browser()

    monkeypatch.setattr(tasks, "launch", fake_launch)
    monkeypatch.setattr(
        tasks, "proxy_config", lambda: {"server": "http://proxy.example:8080"}
    )
    monkeypatch.setattr(
        tasks,
        "storage_state",
        lambda: {"cookies": [{"name": "session"}], "origins": []},
    )
    monkeypatch.setattr(tasks, "_browser", None)
    monkeypatch.setattr(tasks, "_jobs", 0)
    assert (
        tasks._capture("https://www.facebook.com/example.profile")[0] == b"screenshot"
    )
    tasks._capture("https://www.facebook.com/example.profile")
    assert len(launched) == 1
    assert launched[0]["proxy"] == {"server": "http://proxy.example:8080"}
    assert launched[0]["humanize"] is False
    assert contexts[0]["storage_state"]["cookies"][0]["name"] == "session"
