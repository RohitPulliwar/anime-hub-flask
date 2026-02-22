from flask import Blueprint, render_template, redirect , session
from app.routes.auth_route import login_required
main_bp= Blueprint("main_bp", __name__)

@main_bp.route("/")
def home():
    return render_template("index.html")

@main_bp.route("/dashboard")
@login_required
def dashboard():
    # if "user_id" not in session:
    #     return redirect("/login")
    return render_template("dashboard.html")