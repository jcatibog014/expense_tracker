"""Ang Gastos!, a personal expense tracker: income, spending, budgets and charts.

Flask builds the app inside create_app() (the "app factory" pattern).
Tests call it with their own settings, so each test gets a fresh app and database.
"""
import os
from datetime import timedelta
from pathlib import Path

from flask import Flask, render_template

from .money import peso

DEV_SECRET_KEY = "dev-only-not-secret"


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
    )
    if test_config:
        app.config.update(test_config)
    if on_render and app.config["SECRET_KEY"] == DEV_SECRET_KEY:
        raise RuntimeError("Set the SECRET_KEY environment variable on Render.")

    from . import auth, db
    from .views import main

    db.init_app(app)
    auth.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)

    app.jinja_env.filters["peso"] = peso
    app.jinja_env.globals["APP_NAME"] = "Ang Gastos!"

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
