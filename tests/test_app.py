"""The app as a whole: health check, security headers, icons, settings for Render."""
import json
import re
from pathlib import Path

import pytest

from gastos import create_app

STATIC = Path(__file__).parent.parent / "gastos" / "static"


def test_health_check_needs_no_login(client):
    response = client.get("/healthz")
    assert response.status_code == 200 and response.get_json() == {"status": "ok"}


def test_security_headers(client):
    headers = client.get("/login").headers
    csp = headers["Content-Security-Policy"]
    assert "script-src 'self' https://cdn.jsdelivr.net" in csp and "frame-ancestors 'none'" in csp
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" not in headers  # only on Render (HTTPS)


def test_no_inline_scripts(owner_client):
    """The CSP blocks inline scripts, so every page must use script files (JSON data is fine)."""
    for url in ("/login", "/", "/transactions", "/reports", "/budgets", "/data"):
        page = owner_client.get(url, follow_redirects=True).get_data(as_text=True)
        for tag in re.findall(r"<script\b[^>]*>", page):
            assert "src=" in tag or 'type="application/json"' in tag, (url, tag)


def test_app_manifest_and_icons(client):
    page = client.get("/login").get_data(as_text=True)
    for href in re.findall(r'href="/static/([^"]+)"', page):
        assert (STATIC / href).exists(), href
    response = client.get("/static/site.webmanifest")
    assert response.mimetype == "application/manifest+json"
    manifest = json.loads(response.get_data(as_text=True))
    assert manifest["name"] == "Ang Gastos!"
    for icon in manifest["icons"]:
        assert (STATIC / icon["src"]).exists()


def test_render_needs_a_secret_key_and_a_database(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app()
    monkeypatch.setenv("DATABASE_URL", "postgresql://user@example/db")
    app = create_app()
    assert app.config["SESSION_COOKIE_SECURE"] is True
    with app.test_client() as client:
        assert "Strict-Transport-Security" in client.get("/healthz").headers


def test_titles_are_plain_text(owner_client):
    """A <title> must never hold HTML (a template edit once put a whole section in there)."""
    for url in ("/", "/transactions", "/budgets", "/reports", "/wallets", "/settings",
                "/categories", "/repeating", "/data"):
        page = owner_client.get(url).get_data(as_text=True)
        title = re.search(r"<title>(.*?)</title>", page, re.S).group(1)
        assert "<" not in title and title.endswith("Ang Gastos!"), (url, title)


def test_six_tabs_and_the_settings_hub(owner_client):
    page = owner_client.get("/").get_data(as_text=True)
    nav = re.search(r'<nav class="site-nav".*?</nav>', page, re.S).group(0)
    assert re.findall(r">(\w+)</a>", nav) == ["Dashboard", "Transactions", "Budgets", "Reports", "Wallets", "Settings"]
    settings = owner_client.get("/settings").get_data(as_text=True)
    for link in ("/categories", "/repeating", "/data"):
        assert f'href="{link}"' in settings
    # Pages under Settings light up the Settings tab and link back to it.
    categories = owner_client.get("/categories").get_data(as_text=True)
    assert 'aria-current="page">Settings</a>' in categories and "back-link" in categories


def test_the_header_has_no_logo_image(client):
    page = client.get("/login").get_data(as_text=True)
    assert "brand-logo" not in page and "<img" not in page
    assert page.index("Log in</h1>") < page.index("Try the demo")  # the demo card is under the login


def test_old_entries_addresses_still_work(owner_client):
    response = owner_client.get("/entries?month=2026-10&kind=income")
    assert response.status_code == 301 and response.headers["Location"] == "/transactions?month=2026-10&kind=income"
    assert owner_client.get("/entries/5/edit").headers["Location"] == "/transactions/5/edit"
