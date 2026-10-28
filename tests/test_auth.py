from datetime import datetime, timedelta

from gastos import auth, db
from gastos.dates import PH_TIME

from .conftest import OWNER, OWNER_PASSWORD, post

MOMENT = datetime(2026, 10, 28, 9, 0, tzinfo=PH_TIME)


def test_pages_need_a_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login?next=/"


def test_login_page_shows_the_demo_button(client):
    page = client.get("/login").get_data(as_text=True)
    assert "Log in" in page and "Try the demo" in page


def test_log_in_and_out(client):
    response = post(client, "/login", {"username": OWNER, "password": OWNER_PASSWORD})
    assert response.status_code == 302 and response.headers["Location"] == "/"
    assert client.get("/").status_code == 200

    response = post(client, "/logout")
    assert response.headers["Location"] == "/login"
    assert client.get("/").status_code == 302


def test_username_ignores_case_and_spaces(client):
    response = post(client, "/login", {"username": "  JUAN ", "password": OWNER_PASSWORD})
    assert response.status_code == 302


def test_wrong_password_gives_the_same_message_as_unknown_user(client):
    wrong_password = post(client, "/login", {"username": OWNER, "password": "nope"})
    unknown_user = post(client, "/login", {"username": "pedro", "password": "nope"})
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert auth.WRONG_LOGIN in wrong_password.get_data(as_text=True)
    assert auth.WRONG_LOGIN in unknown_user.get_data(as_text=True)


def test_login_goes_back_to_the_page_you_wanted(client):
    response = post(client, "/login", {"username": OWNER, "password": OWNER_PASSWORD, "next": "/settings"})
    assert response.headers["Location"] == "/settings"


def test_login_never_sends_you_to_another_site(app):
    with app.test_request_context():
        for bad in ("https://evil.example", "//evil.example", "/\\evil.example", ""):
            assert auth.safe_next(bad) == "/"
        assert auth.safe_next("/settings") == "/settings"


def test_forms_without_the_csrf_token_are_refused(client):
    response = client.post("/login", data={"username": OWNER, "password": OWNER_PASSWORD})
    assert response.status_code == 400
    response = client.post("/login", data={"username": OWNER, "password": OWNER_PASSWORD, "csrf_token": "wrong"})
    assert response.status_code == 400


def test_five_wrong_passwords_lock_the_account(app):
    with app.app_context():
        for _ in range(auth.MAX_FAILED_LOGINS):
            user, error = auth.check_login(OWNER, "nope", MOMENT)
            assert user is None
        # Locked: even the right password is refused for 15 minutes.
        user, error = auth.check_login(OWNER, OWNER_PASSWORD, MOMENT + timedelta(minutes=14))
        assert user is None and "wait" in error
        user, error = auth.check_login(OWNER, OWNER_PASSWORD, MOMENT + timedelta(minutes=16))
        assert user is not None and error is None


def test_a_right_password_resets_the_count(app):
    with app.app_context():
        for _ in range(auth.MAX_FAILED_LOGINS - 1):
            auth.check_login(OWNER, "nope", MOMENT)
        auth.check_login(OWNER, OWNER_PASSWORD, MOMENT)
        auth.check_login(OWNER, "nope", MOMENT)
        user, error = auth.check_login(OWNER, OWNER_PASSWORD, MOMENT)
        assert user is not None


def test_try_the_demo(client, app):
    response = post(client, "/demo")
    assert response.headers["Location"] == "/"
    page = client.get("/").get_data(as_text=True)
    assert "demo" in page and "Latest transactions" in page
    with app.app_context():
        demo = db.query_one("SELECT * FROM users WHERE is_demo = 1")
        assert demo["username"] == "demo"
        count = db.query_one("SELECT COUNT(*) AS n FROM transactions WHERE user_id = ?", (demo["id"],))["n"]
        assert count > 100


def test_nobody_can_log_in_to_the_demo_with_a_password(client):
    post(client, "/demo")
    post(client, "/logout")
    response = post(client, "/login", {"username": "demo", "password": "demo"})
    assert response.status_code == 401


def test_demo_data_is_reset_after_an_hour(app):
    with app.app_context():
        demo = auth.demo_user(MOMENT)
        db.execute("DELETE FROM transactions WHERE user_id = ?", (demo["id"],))  # a visitor deleted things

        auth.demo_user(MOMENT + timedelta(minutes=30))
        count = db.query_one("SELECT COUNT(*) AS n FROM transactions WHERE user_id = ?", (demo["id"],))["n"]
        assert count == 0  # not yet

        auth.demo_user(MOMENT + timedelta(minutes=61))
        count = db.query_one("SELECT COUNT(*) AS n FROM transactions WHERE user_id = ?", (demo["id"],))["n"]
        assert count > 0


def test_the_demo_cannot_see_the_owners_money(client, app, owner_id):
    with app.app_context():
        cash = db.query_one("SELECT id FROM accounts WHERE user_id = ? AND name = 'Cash'", (owner_id,))["id"]
        salary = db.query_one("SELECT id FROM categories WHERE user_id = ? AND name = 'Salary'", (owner_id,))["id"]
        db.execute(
            """INSERT INTO transactions (user_id, kind, amount, date, account_id, category_id, note)
               VALUES (?, 'income', 99999900, '2026-10-01', ?, ?, 'SECRET BONUS')""",
            (owner_id, cash, salary),
        )
        db.commit()
    post(client, "/demo")
    page = client.get("/").get_data(as_text=True)
    assert "SECRET BONUS" not in page


def test_change_password(owner_client, app):
    response = post(owner_client, "/settings", {
        "current_password": OWNER_PASSWORD, "new_password": "new secret 1", "confirm_password": "new secret 1",
    })
    assert response.status_code == 302
    with app.app_context():
        assert auth.check_login(OWNER, "new secret 1", MOMENT)[0] is not None


def test_change_password_checks_the_form(owner_client):
    response = post(owner_client, "/settings", {
        "current_password": "wrong", "new_password": "short", "confirm_password": "short",
    })
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "isn&#39;t your current password" in page and "at least 8" in page


def test_the_demo_cannot_change_a_password(client):
    post(client, "/demo")
    response = post(client, "/settings", {
        "current_password": "x", "new_password": "new secret 1", "confirm_password": "new secret 1",
    })
    assert response.status_code == 403


def test_create_user_command(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-user", "Maria"], input="long enough\nlong enough\n")
    assert 'Made the user "maria"' in result.output
    with app.app_context():
        assert auth.check_login("maria", "long enough", MOMENT)[0] is not None

    result = runner.invoke(args=["create-user", "maria"], input="long enough\nlong enough\n")
    assert "already exists" in result.output
    result = runner.invoke(args=["create-user", "demo"], input="long enough\nlong enough\n")
    assert "kept for the demo" in result.output


def test_set_password_command(app):
    result = app.test_cli_runner().invoke(args=["set-password", OWNER], input="brand new pw\nbrand new pw\n")
    assert "changed" in result.output
    with app.app_context():
        assert auth.check_login(OWNER, "brand new pw", MOMENT)[0] is not None


def test_reset_demo_command(app):
    result = app.test_cli_runner().invoke(args=["reset-demo"])
    assert "fresh" in result.output
