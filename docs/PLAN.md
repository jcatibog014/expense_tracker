# Roadmap: "Ang Gastos!", a personal expense tracker

The plan agreed on 2026-10-28. Each stage is one branch and one pull request.

## Context

This is a new learning project for the empty repo https://github.com/jcatibog014/expense_tracker (it only has a README).
It records income and expenses, sorts them into categories, and adds up spending by month.
The skills to practise are **SQL, aggregation (SUM / GROUP BY / JOIN), dates and charts**.
It follows the conventions of the other Workspace apps (Flask, plain-function modules, pytest, `.venv`, `AGENTS.md` + `CLAUDE.md`, one PR per stage, Render deploy), as in `Documents\Workspace\weather_app`.

What the owner decided:
- Name **"Ang Gastos!"**, with a **ledger notebook** theme.
- **Login**: one real user (the owner) plus one **demo** account.
- Extras: **monthly budgets, wallets/accounts, CSV import/export, recurring transactions**.
- The owner's real data must survive online. Render's free disk is wiped on every restart, so a SQLite file there won't work.

### Database choice: why not Firestore (as in Moto Garage)
Firestore is a NoSQL document store. It has no SQL, no `GROUP BY` and no `JOIN`, so the whole "practise SQL + aggregation" goal would be lost.
**Recommended: Neon (free, hosted PostgreSQL).** The free plan is permanent, not a trial: about 0.5–1 GB of storage and 100 compute-hours a month, and it sleeps when idle. That is plenty for one person.
- **Local + tests: SQLite** (built into Python, needs no internet; tests never touch the network).
- **Live (Render): Neon Postgres**, used when the `DATABASE_URL` env var is set.
- We write **portable SQL** that runs on both: dates are stored as `'YYYY-MM-DD'` text, months come from `substr(date, 1, 7)`, inserts use `RETURNING id` and upserts use `ON CONFLICT`. Learning the few dialect differences is part of the lesson.
- (Turso, a hosted SQLite, was considered. Its Python driver has no Windows wheels, so it's out.)

## Stack

- Python 3.13, Flask 3, Jinja templates with server-rendered forms (simple, no JS framework). There is a small `app.js` for the charts, month picker and confirm dialogs.
- `sqlite3` (stdlib) + `psycopg[binary]` (Postgres). Raw SQL only, no ORM, so every query is visible and learnable.
- Passwords: `werkzeug.security` (comes with Flask). The CSRF token is hand-rolled in the session, so there's no extra library.
- Charts: **Chart.js 4** from jsDelivr, pinned to an exact version. Every chart also has a "Show as table" view.
- CSV: stdlib `csv`. Tests: pytest. Deploy: Render (Singapore) + Neon (Singapore region, `ap-southeast-1`).
- Money is stored as **integer centavos**, shown as PHP with `₱` (`en-PH` format). The local port is **5002** (5000 = Swap Meter, 5001 = Ambon Alert).

## Folder and package layout

`C:\Users\USER\Documents\Workspace\expense_tracker` (a clone of the repo). The package is `gastos`.

```
gastos/
  __init__.py      create_app(test_config), error handlers, CLI commands
  db.py            get_db(), query()/execute(): one API for SQLite and Postgres
                   (swaps ? -> %s for psycopg), close on teardown
  schema.sql       portable CREATE TABLEs (a tiny per-dialect swap for the id column)
  auth.py          login/logout, login_required, csrf, demo login
  queries.py       ALL the reporting SQL (monthly totals, by category, balances, budgets)
  recurring.py     works out due dates (pure Python) + posts them
  csv_io.py        export/import (parse + validate rows)
  validation.py    form validation -> (data, errors); no Flask import
  seed.py          default categories + demo data generated relative to today
  views/           blueprints: dashboard, transactions, accounts, categories,
                   budgets, recurring, reports, data (csv), settings
  templates/ static/ (style.css, app.js, icons/)
tests/             conftest.py (temp SQLite db, logged-in client fixtures), test_*.py
docs/PLAN.md       roadmap (copy of this plan's stages); docs/screenshots/
AGENTS.md, CLAUDE.md, README.md (A1 English), render.yaml, requirements.txt, .python-version
```

## Data model (every table except users has `user_id`)

| Table | Key columns |
|---|---|
| `users` | id, username UNIQUE, password_hash, is_demo, demo_reset_at |
| `accounts` (wallets) | id, user_id, name, kind (`cash`/`ewallet`/`bank`), opening_balance, archived |
| `categories` | id, user_id, name, kind (`income`/`expense`), color, UNIQUE(user_id, name, kind) |
| `transactions` | id, user_id, account_id, to_account_id (transfers only), category_id (NULL for transfers), kind (`income`/`expense`/`transfer`), amount > 0, date `YYYY-MM-DD`, note, recurring_id, UNIQUE(recurring_id, date) |
| `budgets` | id, user_id, category_id, month `YYYY-MM`, amount, UNIQUE(user_id, category_id, month) |
| `recurring` | id, user_id, account_id, category_id, kind, amount, note, day_of_month, start_date, end_date |

**Privacy rule:** every query filters by `user_id = session user`. Tests check that the demo user can never read, edit or delete the owner's rows (they get a 404).
Transfers move money between wallets and are left out of income/expense totals.

### The SQL to practise (in `queries.py`)
- Monthly totals: `SUM(CASE WHEN kind='expense' THEN amount ELSE 0 END)` … `GROUP BY substr(date,1,7)`.
- Spending by category for a month: `JOIN categories … GROUP BY category ORDER BY total DESC`.
- Budget vs actual: `budgets LEFT JOIN (sub-query of sums)` → spent, left, % used.
- Wallet balances: opening balance + income − expense − transfers out + transfers in.
- Daily running total for the month vs last month (window function `SUM() OVER (ORDER BY date)`, which works in SQLite and Postgres).
- Month-over-month change, average monthly spending, top 5 expenses, a 12-month category × month grid.

## Features by page

- **Login**: username + password. A **"Try the demo"** button logs in as `demo`. The demo data resets (fresh 6 months of sample data, dated relative to today) when someone starts the demo and the last reset was over 1 hour ago. The demo can't change its password and has a capped CSV import. The owner account is created with `flask --app gastos create-user`. There is no public sign-up.
- **Dashboard** (month picker ‹ Oct 2026 ›): income, spending, net and savings-rate tiles; spending-by-category doughnut; 12-month income vs spending bars; budget progress bars; wallet balances; recent transactions; and a "due soon" list of recurring items.
- **Transactions**: a list with filters (month, kind, category, wallet, text search) and paging; add/edit/delete; quick-add form; transfer between wallets.
- **Wallets, Categories**: CRUD. Default categories are made for each new user (Food, Groceries, Transport, Bills, Load/Internet, Rent, Health, Shopping, Fun, Family/Padala, Salary, Freelance, Gifts…). A category or wallet that is in use can be archived but not deleted.
- **Budgets**: set a limit per category per month, plus a "copy last month's budgets" button. Bars turn amber at 80% and red at 100%.
- **Recurring**: rent, salary, subscriptions. When a user opens the app, `post_due()` adds any missed occurrences up to today. `UNIQUE(recurring_id, date)` + `ON CONFLICT DO NOTHING` makes this safe to run again. Day 31 in a short month becomes the month's last day (`calendar.monthrange`).
- **Reports**: a year view with a category × month table, totals and averages, and a cumulative spending line.
- **Import/Export**: download CSV (filtered or all). Upload CSV → preview with per-row errors → confirm. Unknown categories/wallets can be created.
- **Settings**: change password.

## Theme: ledger notebook

Cream "paper" background with faint ruled lines, a red margin line on cards, ink-blue text, **red for spending, green for income**.
Handwritten heading font (e.g. Kalam / Patrick Hand) + a readable body font, with tabular numbers for amounts.
Dark mode is a "night ledger" (dark navy paper, chalk-like ink). Colours are CSS variables on `:root` with both dark-mode blocks (same pattern as Ambon Alert).
Contrast is ≥ 4.5:1, touch targets ≥ 44px, and the phone breakpoint is 520px. The logo is a notebook with a ₱ sign.
Load the `dataviz` skill before building the charts.

## Stages (one branch + PR each)

1. ✅ **Setup, database and login** (this PR also adds `set-password`, a login lock after 5 wrong passwords, and `docs/take_screenshots.py`): clone, `.venv`, skeleton, `db.py` + `schema.sql`, CLI (`init-db`, `create-user`, `reset-demo`), login/logout/CSRF/demo login, base layout + theme basics, AGENTS.md/CLAUDE.md/docs/PLAN.md, tests.
2. ✅ **Wallets, categories, transactions** (category colours are the 8 validated chart colours + gray, stored by name): CRUD, validation, list + filters, privacy tests.
3. **Dashboard, reports and charts**: `queries.py` aggregations + Chart.js + table views + month picker.
4. **Budgets, recurring, transfers**.
5. **CSV import/export**.
6. **Polish and go live**: logo/icons, theme polish, final README (see "README with screenshots" below). The owner creates the Neon project and the Render Blueprint (`render.yaml`: `gastos:create_app()`, `DATABASE_URL` + `SECRET_KEY` generated, region singapore), with step-by-step guidance. Then run `flask create-user` against Neon.

## README with screenshots

The README is in simple (A1) English. It has these parts:
- What the app does
- **Screenshots**
- How to run it
- How to use the demo
- A table of the tools, languages and platforms (Python, Flask, SQLite, PostgreSQL/Neon, Chart.js, Render)

Screenshots live in `docs/screenshots/`. They are taken while logged in as the **demo** account, so no real data shows. The app runs locally, and headless Edge or Chrome captures each page at a fixed size. The README shows them in a table:

| Screenshot | Shows |
|---|---|
| `login.png` | Login page with the "Try the demo" button |
| `dashboard.png` / `dashboard-dark.png` | Month tiles, doughnut + 12-month bars, budgets, wallets (light and dark) |
| `transactions.png` | List with filters |
| `add-transaction.png` | The add form |
| `budgets.png` | Budget progress bars (one amber, one red) |
| `reports.png` | Year view: category × month table + spending line |
| `import.png` | CSV preview with a row error |
| `phone.png` | Dashboard at phone width (390px) |

Each stage's PR adds or updates the README section and screenshots for the pages it built, so the README grows with the app. Stage 6 retakes all of them after the theme polish. Retake any screenshot whenever its page changes visibly; this goes in AGENTS.md as a rule.

Commit messages and PR bodies go through files (`git commit -F`, `gh pr create --body-file`), per the PowerShell note.

## Verification

- `.venv\Scripts\python -m pytest`: unit tests for validation, recurring dates (31st, leap year, end_date), CSV parsing, every `queries.py` function against known seeded rows (exact centavo totals), view tests (login required, CSRF, privacy between users, demo limits).
- Optional Postgres run: `TEST_DATABASE_URL=<Neon test branch>` runs the same query tests on Postgres to prove the SQL is portable.
- Manual: `.venv\Scripts\flask --app gastos run --debug --port 5002`. Log in as the owner and as the demo, add/edit transactions, check that the dashboard totals match the list, check light/dark and phone width.
- After deploy: log in on the live site, restart the Render service, and confirm the owner's data is still there (that is the reason for Neon).
