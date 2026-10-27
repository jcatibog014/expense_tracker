import os

import pytest

from gastos import auth, create_app, db

# Tests use a fresh SQLite file per test. To check the SQL on PostgreSQL too,
# set TEST_DATABASE_URL to an empty Neon branch (its tables are dropped and
# made again for every test, so never point it at the live database).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

CSRF = "test-csrf-token"
OWNER = "juan"
OWNER_PASSWORD = "correct horse"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "DATABASE": str(tmp_path / "test.sqlite"),
        "DATABASE_URL": TEST_DATABASE_URL,
    })
    with app.app_context():
        db.init_db()
        auth.create_user(OWNER, OWNER_PASSWORD)
        db.commit()
    return app


@pytest.fixture
def client(app):
    client = app.test_client()
    # Every POST needs the session's CSRF token. Put a known one in the session.
    with client.session_transaction() as session:
        session["csrf"] = CSRF
    return client


def post(client, url, data=None, **kwargs):
    """POST a form with the right CSRF token, like a real page would."""
    # Logging in or out starts a new session (and a new token), so set it every time.
    with client.session_transaction() as session:
        session["csrf"] = CSRF
    return client.post(url, data={"csrf_token": CSRF, **(data or {})}, **kwargs)


def log_in_as(client, user_id):
    """Skip the login form: put the user straight into the session."""
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["csrf"] = CSRF


def user_id(app, username):
    with app.app_context():
        return db.query_one("SELECT id FROM users WHERE username = ?", (username,))["id"]


def names_to_ids(user_id):
    """({wallet name: id}, {category name: id}) of a user. Needs an app context."""
    accounts = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM accounts WHERE user_id = ?", (user_id,))}
    categories = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM categories WHERE user_id = ?", (user_id,))}
    return accounts, categories


def add_entry(app, user_id, kind, amount, date, account="Cash", category=None, to_account=None, note=""):
    """Put one entry straight into the database. Returns its id."""
    with app.app_context():
        accounts, categories = names_to_ids(user_id)
        if kind != "transfer" and category is None:
            category = "Food" if kind == "expense" else "Salary"
        entry_id = db.insert(
            """INSERT INTO transactions
                   (user_id, kind, amount, date, account_id, to_account_id, category_id, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (user_id, kind, amount, date, accounts[account], accounts.get(to_account),
             categories.get(category), note),
        )
        db.commit()
        return entry_id


def make_user(app, username):
    with app.app_context():
        new_id = auth.create_user(username, "another password")
        db.commit()
        return new_id


@pytest.fixture
def owner_id(app):
    return user_id(app, OWNER)


@pytest.fixture
def other_id(app):
    """A second user, to check that nobody sees another user's money."""
    return make_user(app, "pedro")


@pytest.fixture
def owner_client(client, owner_id):
    log_in_as(client, owner_id)
    return client
