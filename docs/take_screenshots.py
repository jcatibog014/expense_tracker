"""Take the README screenshots (docs/screenshots/*.png).

It logs in with "Try the demo", so no real money shows. It uses Microsoft
Edge, which Windows already has, through Playwright. Playwright is only a
tool for this script, so it is not in requirements.txt:

    .venv\\Scripts\\python -m pip install playwright
    .venv\\Scripts\\flask --app gastos run --port 5002      (in another terminal)
    .venv\\Scripts\\python docs\\take_screenshots.py

Add a line to PAGES when a stage adds a page.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5002"
OUT = Path(__file__).parent / "screenshots"
DESKTOP = {"width": 1200, "height": 800}
PHONE = {"width": 390, "height": 844}

# (file name, address, theme, screen size)
PAGES = [
    ("dashboard.png", "/", "light", DESKTOP),
    ("dashboard-dark.png", "/", "dark", DESKTOP),
    ("phone.png", "/", "light", PHONE),
    ("transactions.png", "/entries", "light", DESKTOP),
    ("add-transaction.png", "/entries/new", "light", DESKTOP),
    ("wallets.png", "/wallets", "light", DESKTOP),
    ("categories.png", "/categories", "light", DESKTOP),
    ("reports.png", "/reports", "light", DESKTOP),
    ("budgets.png", "/budgets", "light", DESKTOP),
    ("repeating.png", "/repeating", "light", DESKTOP),
    ("transactions-phone.png", "/entries", "dark", PHONE),
]


def shoot(browser, name, path, theme, size):
    page = browser.new_page(viewport=size, color_scheme=theme)
    page.goto(f"{BASE}/login")
    page.get_by_role("button", name="Try the demo").click()
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")  # fonts and Chart.js are in
    page.wait_for_timeout(800)  # let the charts finish drawing
    page.screenshot(path=OUT / name, full_page=size is DESKTOP)
    page.close()
    print("saved", name)


def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")

        page = browser.new_page(viewport=DESKTOP, color_scheme="light")
        page.goto(f"{BASE}/login")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=OUT / "login.png")
        page.close()
        print("saved login.png")

        for name, path, theme, size in PAGES:
            shoot(browser, name, path, theme, size)
        browser.close()


if __name__ == "__main__":
    main()
