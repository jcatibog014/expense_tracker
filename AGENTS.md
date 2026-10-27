# AGENTS.md

This file guides AI coding agents (Claude Code, Codex, Cursor, Copilot and others) working in this repository.

## Overview

**Ang Gastos!**, a personal expense tracker in Python (Flask). The repo is `expense_tracker` and the Python package is `gastos`. It records income, spending and transfers between wallets, sorts them into categories, and totals them by month. Budgets, recurring items, CSV import/export and charts come in later stages (see `docs/PLAN.md`). It is a learning project for **SQL, aggregation, dates and charts**, so all database access is raw SQL (no ORM). Keep the code readable for a learner: short comments that explain *why*, and no extra libraries unless the owner asks for them. Write the README in simple (A1-level) English.

Python 3.13 is at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`. Use the virtual environment:

- Install: `.venv\Scripts\python -m pip install -r requirements.txt` (create `.venv` with `python -m venv .venv` first if it's missing).
- First time: `.venv\Scripts\flask --app gastos init-db`, then `.venv\Scripts\flask --app gastos create-user <name>`.
- Run: `.venv\Scripts\flask --app gastos run --debug --port 5002`, then open http://127.0.0.1:5002. (Port 5002: Swap Meter uses 5000, Ambon Alert 5001.)
- Test: `.venv\Scripts\python -m pytest`. Tests use a fresh SQLite file each and never use the internet. Set `TEST_DATABASE_URL` to an **empty** Neon branch to run the same tests on PostgreSQL (each test drops and remakes the tables).
- Other commands: `set-password <name>`, `reset-demo`, `init-db --yes` (deletes everything).

## Architecture

- **Two databases, one SQL.** `gastos/db.py` connects to SQLite (`instance/gastos.sqlite`, git-ignored) or, when `DATABASE_URL` is set, to PostgreSQL with psycopg (Neon on the live site). Use `db.query()`, `query_one()`, `execute()`, `execute_many()`, `insert()` (for `INSERT ... RETURNING id`) and `commit()`. Rows come back as dicts. Write `?` placeholders; `_sql()` turns them into `%s` (and `%` into `%%`) for psycopg. Never put values into the SQL text. Nothing is saved without `commit()`; the connection closes at the end of each request.
- Keep SQL portable: dates are `'YYYY-MM-DD'` text and months are `substr(date, 1, 7)`; there is no `strftime()`/`to_char()`. True/false is `0/1`. Use `RETURNING id`, `ON CONFLICT`, `COALESCE`, `CASE`. In `schema.sql`, `id INTEGER PRIMARY KEY` is rewritten for Postgres by `schema_sql()`, so keep that exact spelling.
- `gastos/schema.sql`: `users`, `accounts` (wallets), `categories`, `recurring`, `transactions`, `budgets`. Money is **integer centavos**. A transaction's `kind` is `income`, `expense` or `transfer`; a CHECK makes transfers have `to_account_id` and no category, and the others the opposite. A wallet or category that is still used can't be deleted (FOREIGN KEY), so the app archives it. `UNIQUE (recurring_id, date)` makes posting a recurring item safe to repeat.
- **Privacy:** every table except `users` has `user_id`, and every query must filter on `g.user["id"]`. A row of another user must give 404. Tests check that the demo can't see the owner's data.
- `gastos/auth.py`: login/logout (`/login`, `POST /logout`), `POST /demo`, `/settings` (change password), `login_required`, `g.user` (`id`, `username`, `is_demo`), and the CLI commands. No sign-up page. Usernames are lower-cased. Wrong logins say the same `WRONG_LOGIN` whether or not the user exists; 5 wrong passwords lock the account for 15 minutes (`failed_logins`, `locked_until`). Login starts a fresh session (`log_in()`), and `safe_next()` only allows paths on this site.
- **CSRF:** every POST form needs `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`; `check_csrf()` refuses others with 400. Tests use `post()` from `tests/conftest.py`, which sets the token.
- **The demo** is the user with `is_demo = 1` (username `demo`, a random password nobody knows). `demo_user()` makes it on first use and calls `seed.reset_demo()` when `demo_reset_at` is over an hour old. The demo can't change its password.
- `gastos/seed.py`: `DEFAULT_ACCOUNTS`/`DEFAULT_CATEGORIES` for every new user (`add_defaults()`), and `demo_transactions(today)`, 6 months of Metro Manila-style sample money dated relative to today. It is deterministic per date (`random.Random(today.isoformat())`).
- `gastos/dates.py`: `today()`/`now()` are in Philippine time (`PH_TIME`, a fixed UTC+8, because Windows has no tz database without the `tzdata` package and the PH has no daylight saving). There are also month helpers (`add_months`, `day_in_month`, `month_label`, ...).
- `gastos/money.py`: `peso(centavos, signed=False)` (also the Jinja filter `peso`).
- `gastos/views/`: one blueprint per area. `main.home` (`/`) shows this month's totals and the latest entries.
- `gastos/__init__.py`: `create_app(test_config)`, config from env (`SECRET_KEY`, `DATABASE_URL`, and `RENDER` makes cookies HTTPS-only and requires a real `SECRET_KEY`), and error pages (`error.html`).

### Front end

- Server-rendered Jinja pages with plain HTML forms; they work without JavaScript. `static/app.js` only adds extras (now: the theme toggle; later: charts).
- DOM text goes in with `textContent`, never `innerHTML`.

## Conventions

- Brand: "Ang Gastos!" (`APP_NAME` Jinja global, the `<title>`s, and the header `Ang <em>Gastos!</em>`, where `Gastos!` is red). The logo is `static/icons/logo.svg` (a notebook page with a ₱).
- Theme "ledger notebook": cream paper with ruled lines (`body` background), `.card` with a red margin line (`::before`), ink-blue text, `--income` green and `--expense` red. Fonts: Kalam (headings, brand) and Source Sans 3 (body), from Google Fonts; amounts use `tabular-nums`.
- Styling: `static/style.css`, colours as CSS variables on `:root`. Dark mode ("night ledger") redefines them under `prefers-color-scheme: dark` (unless `data-theme="light"`) and under `[data-theme="dark"]`; change both blocks together. The phone breakpoint is 520px.
- Accessibility: text ≥ 4.5:1 and `--control-border` ≥ 3:1 against `--paper` and `--card` in both themes. Touch targets ≥ 44px. Form errors use `aria-invalid` + `aria-describedby`.
- Show money with the `peso` filter. Income is `amount-income` (green, "+"), spending is `amount-expense` (red, "−").
- Keep comments teaching-oriented but brief. Add or update a test with every behaviour change.
- **Screenshots:** README screenshots live in `docs/screenshots/` and are taken as the demo user with `docs/take_screenshots.py` (Playwright + Edge; install Playwright separately, it is not in requirements). Add new pages to its `PAGES` list, and retake the screenshots whenever a page changes visibly.
- Git: one branch + PR per stage of `docs/PLAN.md`. On this Windows machine, pass commit messages and PR bodies as files (`git commit -F`, `gh pr create --body-file`).
