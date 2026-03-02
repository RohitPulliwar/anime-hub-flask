import sqlite3
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import create_user, get_user_by_username

auth_bp = Blueprint("auth_bp", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Please fill in both username and password.")
        return redirect(url_for("auth_bp.register"))

    if len(password) < 6:
        flash("Password must be at least 6 characters.")
        return redirect(url_for("auth_bp.register"))

    try:
        create_user(username, generate_password_hash(password))
    except sqlite3.IntegrityError:
        flash("That username is already taken.")
        return redirect(url_for("auth_bp.register"))

    flash("Account created. You can log in now.")
    return redirect(url_for("auth_bp.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    user = get_user_by_username(username)

    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        flash("Welcome back.")
        return redirect(url_for("main_bp.dashboard"))

    flash("Invalid username or password.")
    return redirect(url_for("auth_bp.login"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("main_bp.home"))


def login_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.")
            return redirect(url_for("auth_bp.login"))
        return handler(*args, **kwargs)

    return wrapped
