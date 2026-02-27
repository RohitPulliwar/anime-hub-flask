from flask import Blueprint, render_template, redirect , session, flash,request,url_for,current_app
from app.routes.auth_route import login_required
import requests
import sqlite3
import time 
from app.db import update_user_avatar,get_status_db,save_status_db,get_user_by_id,get_db_connection,get_user_favorites_with_status
import os
import re
from uuid import uuid4


quiz_questions = [
    {
        "question": "Who is Naruto's father?",
        "options": ["Kakashi", "Minato", "Jiraiya", "Itachi"],
        "answer": "Minato"
    },
    {
        "question": "Which anime has Titans?",
        "options": ["Bleach", "One Piece", "Attack on Titan", "Dragon Ball"],
        "answer": "Attack on Titan"
    },
    {
        "question": "Who is Goku's first son?",
        "options": ["Goten", "Vegeta", "Gohan", "Trunks"],
        "answer": "Gohan"
    },
    {
        "question": "Who uses Death Note?",
        "options": ["L", "Naruto", "Light Yagami", "Asta"],
        "answer": "Light Yagami"
    },
    {
        "question": "Blue Lock is about?",
        "options": ["Basketball", "Football", "Cooking", "Magic"],
        "answer": "Football"
    }
]


dashboard_cache={}
CACHE_TIMEOUT=300
main_bp= Blueprint("main_bp", __name__)

@main_bp.route("/")
def home():

    
    url = "https://api.jikan.moe/v4/anime?order_by=popularity&sort=asc&limit=12"
    response = requests.get(url)
    trending = response.json().get("data", [])

    return render_template("index.html", trending=trending)
@main_bp.route("/dashboard")
@login_required
def dashboard():

    username = session.get("username")
    current_time = time.time()

   
    if "top" in dashboard_cache and current_time - dashboard_cache["top_time"] < CACHE_TIMEOUT:
        top_anime = dashboard_cache["top"]
    else:
        top_url = "https://api.jikan.moe/v4/top/anime?limit=10"
        response = requests.get(top_url)
        top_anime = response.json().get("data", [])
        dashboard_cache["top"] = top_anime
        dashboard_cache["top_time"] = current_time

 
    if "seasonal" in dashboard_cache and current_time - dashboard_cache["seasonal_time"] < CACHE_TIMEOUT:
        seasonal_anime = dashboard_cache["seasonal"]
    else:
        season_url = "https://api.jikan.moe/v4/seasons/now"
        response = requests.get(season_url)
        seasonal_anime = response.json().get("data", [])[:10]
        dashboard_cache["seasonal"] = seasonal_anime
        dashboard_cache["seasonal_time"] = current_time

   
    if "popular" in dashboard_cache and current_time - dashboard_cache["popular_time"] < CACHE_TIMEOUT:
        popular_anime = dashboard_cache["popular"]
    else:
        popular_url = "https://api.jikan.moe/v4/anime?order_by=popularity&sort=asc&limit=10"
        response = requests.get(popular_url)
        popular_anime = response.json().get("data", [])
        dashboard_cache["popular"] = popular_anime
        dashboard_cache["popular_time"] = current_time

    return render_template(
        "dashboard.html",
        username=username,
        top_anime=top_anime,
        seasonal_anime=seasonal_anime,
        popular_anime=popular_anime
    )
@main_bp.route("/search", methods=["GET", "POST"])
def search():
    results = []
    favorite_ids = []

    if request.method == "POST":
        query = request.form.get("anime_name")

        if query:
            url = f"https://api.jikan.moe/v4/anime?q={query}"
            response = requests.get(url)
            data = response.json()
            results = data.get("data", [])

            
            if "user_id" in session:
                conn = get_db_connection()
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT anime_id FROM favorites WHERE user_id=?",
                    (session["user_id"],)
                )

                rows = cursor.fetchall()
                favorite_ids = [row[0] for row in rows]

                conn.close()

    return render_template(
        "search.html",
        results=results,
        favorite_ids=favorite_ids
    )

@main_bp.route("/anime/<int:anime_id>",methods=["GET","POST"])
def anime_detail(anime_id):


    if request.method=="POST" and "user_id" in session:
        status=request.form.get("status")
        if status:
            save_status_db(session.get("user_id"), anime_id,status)
    url = f"https://api.jikan.moe/v4/anime/{anime_id}"
    response = requests.get(url)
    data = response.json()
    anime = data.get("data")

    is_favorite = False

    if "user_id" in session:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM favorites WHERE user_id=? AND anime_id=?",
            (session["user_id"], anime_id)
        )

        if cursor.fetchone():
            is_favorite = True

        conn.close()

    my_status=None
    if "user_id" in session:
        my_status=get_status_db(session["user_id"],anime_id)
    return render_template(
        "anime_detail.html",
        anime=anime,
        is_favorite=is_favorite,
        my_status=my_status
    )

@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():

    user_id = int(session.get("user_id"))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("SELECT banner_url FROM users WHERE id = ?", (user_id,))
        current_user = cursor.fetchone()
        bio = (request.form.get("bio") or "").strip()
        banner_url = current_user["banner_url"] if current_user else ""
        theme_color = (request.form.get("theme_color") or "").strip()
        banner_file = request.files.get("banner_file")

        if len(bio) > 220:
            bio = bio[:220]

        if banner_file and banner_file.filename:
            ext = banner_file.filename.rsplit(".", 1)[-1].lower() if "." in banner_file.filename else ""
            allowed_exts = {"png", "jpg", "jpeg", "webp", "gif"}
            if ext in allowed_exts:
                banner_folder = os.path.join(current_app.root_path, "static", "profile_banners")
                os.makedirs(banner_folder, exist_ok=True)
                filename = f"{uuid4().hex}.{ext}"
                save_path = os.path.join(banner_folder, filename)
                banner_file.save(save_path)
                banner_url = url_for("static", filename=f"profile_banners/{filename}")
            else:
                flash("Invalid banner format. Use PNG, JPG, JPEG, WEBP, or GIF.")

        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", theme_color):
            theme_color = "#40e0d0"

        cursor.execute(
            """
            UPDATE users
            SET bio = ?, banner_url = ?, theme_color = ?
            WHERE id = ?
            """,
            (bio, banner_url, theme_color, user_id),
        )
        conn.commit()
        flash("Profile style updated.")

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    favorites = get_user_favorites_with_status(user_id)
    total_favorites = len(favorites)

    status_order = ["Watching", "Completed", "Plan to Watch", "Dropped", "Not Set"]
    grouped_favorites = {status: [] for status in status_order}

    for fav in favorites:
        status = fav["status"] if fav["status"] else "Not Set"
        if status not in grouped_favorites:
            grouped_favorites["Not Set"].append(fav)
        else:
            grouped_favorites[status].append(fav)

    status_counts = {status: len(grouped_favorites[status]) for status in status_order}
    completed_count = status_counts["Completed"]
    completion_rate = int((completed_count / total_favorites) * 100) if total_favorites else 0

    cursor.execute(
        "SELECT COUNT(*) as total FROM quiz_attempts WHERE user_id=?",
        (user_id,),
    )
    quiz_result = cursor.fetchone()
    quiz_count = quiz_result["total"] if quiz_result else 0

    conn.close()

    if user["next_level_xp"] > 0:
        xp_percentage = int(
            (user["current_xp"] / user["next_level_xp"]) * 100
        )
    else:
        xp_percentage = 0

    return render_template(
        "profile.html",
        user=user,
        xp_percentage=xp_percentage,
        favorites=favorites,
        grouped_favorites=grouped_favorites,
        status_order=status_order,
        status_counts=status_counts,
        completion_rate=completion_rate,
        total_favorites=total_favorites,
        quiz_count=quiz_count,
        fav_count=total_favorites,
        badges=[],
        avatar_items=[],
    )

@main_bp.route("/choose-avatar", methods=["GET", "POST"])
@login_required
def choose_avatar():

    user_id = session.get("user_id")
    user = get_user_by_id(user_id)

    avatar_folder = os.path.join("app", "static", "profile_pics")
    avatar_list = os.listdir(avatar_folder)

    if request.method == "POST":
        selected_avatar = request.form.get("avatar")

        if selected_avatar in avatar_list:
            update_user_avatar(user_id, selected_avatar)

        return redirect(url_for("main_bp.profile"))

    return render_template(
        "choose_avatar.html",
        avatars=avatar_list,
        user=user
    )
