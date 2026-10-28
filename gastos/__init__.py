"""Ang Gastos!, a personal expense tracker: income, spending, budgets and charts.

Flask builds the app inside create_app() (the "app factory" pattern).
Tests call it with their own settings, so each test gets a fresh app and database.
"""
import mimetypes
import os
from datetime import timedelta
from pathlib import Path

from flask import Flask, render_template

# Python doesn't know this file type, and browsers want the right one for
# the app manifest (the name and icons used by "Add to Home Screen").
mimetypes.add_type("application/manifest+json", ".webmanifest")

from .dates import short_date
from .money import peso

DEV_SECRET_KEY = "dev-only-not-secret"

# Content-Security-Policy: the browser may only load scripts, styles, fonts
# and images from these places. If someone ever sneaked a <script> into a
# page (in a note, say), the browser would refuse to run it.
# 'unsafe-inline' for styles only: some templates set a bar's width in style="".
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    on_render = bool(os.environ.get("RENDER"))  # Render sets RENDER=true on its servers
    app.config.from_mapping(
        # Signs the login cookie. On Render it comes from an environment variable.
        SECRET_KEY=os.environ.get("SECRET_KEY", DEV_SECRET_KEY),
        # Local SQLite file, in the instance/ folder (git ignores it).
        DATABASE=str(Path(app.instance_path) / "gastos.sqlite"),
        # Set on the live site: then we use PostgreSQL (Neon) instead of SQLite.
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        # Cookie safety: not readable by JavaScript (Flask's default), not sent
        # with forms from other sites, and only over HTTPS on the live site.
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=on_render,
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,  # the biggest upload (a CSV file) we accept
        # The CSV preview sends the file's text back as a form field; allow that much.
        MAX_FORM_MEMORY_SIZE=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if on_render and app.config["SECRET_KEY"] == DEV_SECRET_KEY:
        raise RuntimeError("Set the SECRET_KEY environment variable on Render.")
    if on_render and not app.config["DATABASE_URL"]:
        # Without it we'd use a SQLite file, and Render forgets files on every restart.
        raise RuntimeError("Set the DATABASE_URL environment variable on Render (Neon's connection string).")

    from . import auth, db
    from .views import budgets, categories, data, main, repeating, reports, transactions, wallets

    db.init_app(app)
    auth.init_app(app)
    # auth comes first: its before_request (load_user) must run before the others'.
    for blueprint in (auth.bp, main.bp, transactions.bp, wallets.bp, categories.bp, reports.bp,
                      budgets.bp, repeating.bp, data.bp):
        app.register_blueprint(blueprint)

    app.jinja_env.filters["peso"] = peso
    app.jinja_env.filters["short_date"] = short_date
    app.jinja_env.globals["APP_NAME"] = "Ang Gastos!"

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")  # trust our file types
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")  # no showing us inside other sites
        if on_render:
            # Always use HTTPS for this site from now on (for a year).
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    def error_page(code, message):
        return render_template("error.html", code=code, message=message), code

    @app.errorhandler(400)
    def bad_request(error):
        return error_page(400, error.description or "Something in that request was wrong.")

    @app.errorhandler(403)
    def forbidden(error):
        return error_page(403, error.description or "You can't do that.")

    @app.errorhandler(404)
    def not_found(error):
        return error_page(404, "We couldn't find that page.")

    @app.errorhandler(413)
    def too_large(error):
        return error_page(413, "That file is too big.")

    return app
