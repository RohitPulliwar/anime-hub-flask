import os
import secrets

from flask import Flask, abort, request, session

from .db import init_db


def create_app():
    app = Flask(__name__)
    is_production = os.getenv("FLASK_ENV", "").lower() in {"production", "prod"} or os.getenv("APP_ENV", "").lower() in {"production", "prod"}
    secret_key = os.getenv("FLASK_SECRET_KEY")
    if is_production and not secret_key:
        raise RuntimeError("FLASK_SECRET_KEY must be set in production.")

    app.secret_key = secret_key or "dev-only-change-me"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = is_production
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload cap

    def _csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    app.jinja_env.globals["csrf_token"] = _csrf_token

    @app.before_request
    def _csrf_protect():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        if request.path.startswith("/static/"):
            return

        session_token = session.get("_csrf_token")
        request_token = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")
        if not session_token or not request_token or not secrets.compare_digest(session_token, request_token):
            abort(400, description="Invalid CSRF token.")

    init_db()

    from .routes.auth_route import auth_bp
    from .routes.favorite_route import fav_bp
    from .routes.main_route import main_bp
    from .routes.quiz_route import quiz_bp
    from .routes.comment_route import comment_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(fav_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(comment_bp)

    return app
