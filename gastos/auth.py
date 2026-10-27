"""Logging in and out, the demo account, and protection for every form.

There is no sign-up page. The owner's account is made on the command line:

    flask --app gastos create-user <name>

Anyone can press "Try the demo", which logs in as the shared demo user.
Every table has a user_id, and every query filters on g.user["id"], so the
demo can never see the owner's money (tests/test_auth.py checks this).
"""
import functools
import hmac
import secrets
from datetime import timedelta

import click
from flask import (
    Blueprint, abort, flash, g, redirect, render_template, request, session, url_for,
)
from flask.cli import with_appcontext
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, seed
from .dates import now

bp = Blueprint("auth", __name__)

USERNAME_MAX_LENGTH = 40
PASSWORD_MIN_LENGTH = 8
# After 5 wrong passwords in a row, the account waits 15 minutes.
# This makes guessing the owner's password on the live site very slow.
MAX_FAILED_LOGINS = 5
LOCK_TIME = timedelta(minutes=15)

DEMO_USERNAME = "demo"
# Many visitors share the demo. Its data is made fresh when someone starts
# the demo and the last reset was more than an hour ago.
DEMO_RESET_AFTER = timedelta(hours=1)

WRONG_LOGIN = "Wrong username or password."


# ---------- Users in the database ----------

def clean_username(text):
    return (text or "").strip().lower()


def create_user(username, password, is_demo=False):
    """Add a user with the default wallets and categories. The caller commits."""
    user_id = db.insert(
        "INSERT INTO users (username, password_hash, is_demo) VALUES (?, ?, ?) RETURNING id",
        (clean_username(username), generate_password_hash(password), int(is_demo)),
    )
    seed.add_defaults(user_id)
    return user_id


def set_password(user_id, password):
    db.execute(
        "UPDATE users SET password_hash = ?, failed_logins = 0, locked_until = NULL WHERE id = ?",
        (generate_password_hash(password), user_id),
    )


def check_login(username, password, moment):
    """Return (user, None) if the password is right, else (None, message).

    The message never says whether the username exists, so a stranger
    can't use the login form to find out the owner's username.
    """
    user = db.query_one(
        "SELECT * FROM users WHERE username = ? AND is_demo = 0", (clean_username(username),)
    )
    if user is None:
        return None, WRONG_LOGIN

    # The times are ISO text, so comparing them as text compares the times.
    if user["locked_until"] and user["locked_until"] > moment.isoformat():
        return None, "Too many wrong tries. Please wait 15 minutes and try again."

    if not check_password_hash(user["password_hash"], password or ""):
        failed = user["failed_logins"] + 1
        locked_until = None
        if failed >= MAX_FAILED_LOGINS:
            failed, locked_until = 0, (moment + LOCK_TIME).isoformat()
        db.execute(
            "UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
            (failed, locked_until, user["id"]),
        )
        db.commit()
        return None, WRONG_LOGIN

    db.execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (user["id"],))
    db.commit()
    return user, None


def demo_user(moment, force_reset=False):
    """The demo user, made (or made fresh) when needed. The caller commits."""
    user = db.query_one("SELECT * FROM users WHERE is_demo = 1")
    if user is None:
        # Nobody knows this password: the demo is only opened with the button.
        create_user(DEMO_USERNAME, secrets.token_urlsafe(32), is_demo=True)
        user = db.query_one("SELECT * FROM users WHERE is_demo = 1")

    last_reset = user["demo_reset_at"]
    if force_reset or last_reset is None or last_reset < (moment - DEMO_RESET_AFTER).isoformat():
        seed.reset_demo(user["id"], moment.date())
        db.execute("UPDATE users SET demo_reset_at = ? WHERE id = ?", (moment.isoformat(), user["id"]))
    return user


def safe_next(target, default=None):
    """Only go back to a page on this site (after logging in or saving a form).

    "/entries" is fine. "https://evil.example" and "//evil.example"
    are not: a fake link could send people there after a real login.
    """
    if target and target.startswith("/") and not target.startswith(("//", "/\\")):
        return target
    return default or url_for("main.home")


def log_in(user):
    session.clear()  # a new session for the new user (old cookies can't be reused)
    session.permanent = True  # stay logged in for PERMANENT_SESSION_LIFETIME
    session["user_id"] = user["id"]


# ---------- Every request ----------

@bp.before_app_request
def load_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = db.query_one(
            "SELECT id, username, is_demo FROM users WHERE id = ?", (user_id,)
        )


def csrf_token():
    """A secret per session, put into every form as a hidden field.

    Another website could make your browser send a form to this site (your
    login cookie goes with it). It can't read this secret, so its form fails.
    """
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


@bp.before_app_request
def check_csrf():
    if request.method != "POST":
        return
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf", "")
    # compare_digest takes the same time for every wrong guess.
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "This form has expired. Please go back, reload the page and try again.")


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


# ---------- Pages ----------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("main.home"))
    next_page = request.values.get("next", "")
    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "")[:USERNAME_MAX_LENGTH]
        user, error = check_login(username, request.form.get("password", ""), now())
        if user:
            log_in(user)
            return redirect(safe_next(next_page))
    status = 401 if error else 200
    return render_template("login.html", error=error, username=username, next=next_page), status


@bp.post("/demo")
def demo():
    user = demo_user(now())
    db.commit()
    log_in(user)
    flash("Welcome to the demo! The money here is made up, so feel free to try anything.")
    return redirect(url_for("main.home"))


@bp.post("/logout")
def logout():
    session.clear()
    flash("You are logged out.")
    return redirect(url_for("auth.login"))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    errors = {}
    if request.method == "POST":
        if g.user["is_demo"]:
            abort(403, "The demo account can't change its password.")
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        user = db.query_one("SELECT password_hash FROM users WHERE id = ?", (g.user["id"],))
        if not check_password_hash(user["password_hash"], current):
            errors["current_password"] = "That isn't your current password."
        if len(new) < PASSWORD_MIN_LENGTH:
            errors["new_password"] = f"Use at least {PASSWORD_MIN_LENGTH} characters."
        elif new != request.form.get("confirm_password", ""):
            errors["confirm_password"] = "The two new passwords are not the same."
        if not errors:
            set_password(g.user["id"], new)
            db.commit()
            flash("Your password is changed.")
            return redirect(url_for("auth.settings"))
    return render_template("settings.html", errors=errors), 400 if errors else 200


# ---------- Command line ----------

def ask_password():
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    if len(password) < PASSWORD_MIN_LENGTH:
        raise click.ClickException(f"Use at least {PASSWORD_MIN_LENGTH} characters.")
    return password


@click.command("create-user")
@with_appcontext
@click.argument("username")
def create_user_command(username):
    """Make a login (with the default wallets and categories)."""
    username = clean_username(username)
    if not username or len(username) > USERNAME_MAX_LENGTH:
        raise click.ClickException(f"Use 1 to {USERNAME_MAX_LENGTH} characters for the username.")
    if username == DEMO_USERNAME:
        raise click.ClickException('"demo" is kept for the demo account.')
    if db.query_one("SELECT id FROM users WHERE username = ?", (username,)):
        raise click.ClickException(f'"{username}" already exists. Use set-password to change the password.')
    create_user(username, ask_password())
    db.commit()
    click.echo(f'Made the user "{username}".')


@click.command("set-password")
@with_appcontext
@click.argument("username")
def set_password_command(username):
    """Change a user's password (and unlock the account)."""
    user = db.query_one(
        "SELECT id FROM users WHERE username = ? AND is_demo = 0", (clean_username(username),)
    )
    if user is None:
        raise click.ClickException(f'There is no user "{username}".')
    set_password(user["id"], ask_password())
    db.commit()
    click.echo("The password is changed.")


@click.command("reset-demo")
@with_appcontext
def reset_demo_command():
    """Make the demo data fresh now."""
    demo_user(now(), force_reset=True)
    db.commit()
    click.echo("The demo data is fresh.")


def init_app(app):
    app.jinja_env.globals["csrf_token"] = csrf_token
    for command in (create_user_command, set_password_command, reset_demo_command):
        app.cli.add_command(command)
