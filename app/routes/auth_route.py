from flask import Blueprint, render_template, request, redirect, flash, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from app.db import create_user, get_user_by_username

auth_bp = Blueprint("auth_bp", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if not username or not password:
            flash("All fields are required")
            return redirect(url_for("auth_bp.register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters")
            return redirect(url_for("auth_bp.register"))

        hashed_pass = generate_password_hash(password)

        try:
            create_user(username, hashed_pass)
            flash("Registration completed")
            return redirect(url_for("auth_bp.login"))
        except:
            flash("User already exists")

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = get_user_by_username(username)

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Login successful")
            return redirect(url_for("main_bp.dashboard"))
        else:
            flash("Incorrect data")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully")
    return redirect(url_for("main_bp.home"))


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("login first")
            return redirect(url_for("auth_bp.login"))
        return f(*args, **kwargs)
    return wrapper