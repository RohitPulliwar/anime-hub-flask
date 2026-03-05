import os
import re
import time
from uuid import uuid4

import requests
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.db import (
    get_db_connection,
    get_status_db,
    get_user_by_id,
    get_user_favorites_with_status,
    save_status_db,
    update_user_avatar,
)
from app.routes.auth_route import login_required

main_bp = Blueprint("main_bp", __name__)

API_CACHE = {}
CACHE_TTL_SECONDS = 300
VALID_STATUS = ["Watching", "Completed", "Plan to Watch", "Dropped", "Not Set"]
DEFAULT_THEME = "#40e0d0"
MEDIA_LABELS = {
    "anime": "Anime",
    "manga": "Manga",
    "lightnovel": "Light Novel",
}
PROFILE_MEDIA_ORDER = ["anime", "manga", "lightnovel"]


def _get_media_type():
    media_type = (request.args.get("media") or "anime").strip().lower()
    return media_type if media_type in MEDIA_LABELS else "anime"


def _media_extra_params(media_type):
    if media_type == "manga":
        return {"type": "manga"}
    if media_type == "lightnovel":
        return {"type": "novel"}
    return {}


def _api_resource(media_type):
    return "anime" if media_type == "anime" else "manga"


def _fetch_json(url, params=None):
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _fetch_cached_list(cache_key, url, params=None, limit=None):
    now = time.time()
    full_cache_key = f"{cache_key}:{url}:{str(params)}:{limit}"
    cached = API_CACHE.get(full_cache_key)

    if cached and now - cached["at"] < CACHE_TTL_SECONDS:
        data = cached["payload"]
    else:
        data = _fetch_json(url, params=params).get("data", [])
        API_CACHE[full_cache_key] = {"payload": data, "at": now}

    return data[:limit] if limit else data


def _load_favorite_ids(user_id, media_type):
    connection = get_db_connection()
    rows = connection.execute(
        "SELECT anime_id FROM favorites WHERE user_id = ? AND media_type = ?",
        (user_id, media_type),
    ).fetchall()
    connection.close()
    return [row[0] for row in rows]


def _save_profile_customization(cursor, user_id):
    current_user = cursor.execute(
        "SELECT banner_url FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    bio = (request.form.get("bio") or "").strip()[:220]
    theme_color = (request.form.get("theme_color") or "").strip()
    banner_url = current_user["banner_url"] if current_user else ""
    uploaded_banner = request.files.get("banner_file")

    if uploaded_banner and uploaded_banner.filename:
        extension = (
            uploaded_banner.filename.rsplit(".", 1)[-1].lower()
            if "." in uploaded_banner.filename
            else ""
        )
        allowed = {"png", "jpg", "jpeg", "webp", "gif"}

        if extension in allowed:
            banner_dir = os.path.join(current_app.root_path, "static", "profile_banners")
            os.makedirs(banner_dir, exist_ok=True)
            file_name = f"{uuid4().hex}.{extension}"
            upload_path = os.path.join(banner_dir, file_name)
            uploaded_banner.save(upload_path)
            banner_url = url_for("static", filename=f"profile_banners/{file_name}")
        else:
            flash("Banner file must be PNG, JPG, JPEG, WEBP, or GIF.")

    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", theme_color):
        theme_color = DEFAULT_THEME

    cursor.execute(
        """
        UPDATE users
        SET bio = ?, banner_url = ?, theme_color = ?
        WHERE id = ?
        """,
        (bio, banner_url, theme_color, user_id),
    )
    flash("Profile updated.")


def _build_profile_groups(favorites):
    grouped = {label: [] for label in VALID_STATUS}
    for anime in favorites:
        status = anime["status"] if anime["status"] else "Not Set"
        grouped[status if status in grouped else "Not Set"].append(anime)
    return grouped


@main_bp.route("/")
def home():
    media_type = _get_media_type()
    resource = _api_resource(media_type)
    params = {"order_by": "popularity", "sort": "asc", "limit": 12}
    params.update(_media_extra_params(media_type))

    trending = _fetch_json(f"https://api.jikan.moe/v4/{resource}", params=params).get("data", [])
    favorite_ids = (
        _load_favorite_ids(session["user_id"], media_type) if "user_id" in session else []
    )

    return render_template(
        "index.html",
        trending=trending,
        favorite_ids=favorite_ids,
        current_media=media_type,
        media_label=MEDIA_LABELS[media_type],
    )


@main_bp.route("/dashboard")
@login_required
def dashboard():
    media_type = _get_media_type()
    resource = _api_resource(media_type)
    username = session.get("username")
    favorite_ids = _load_favorite_ids(session["user_id"], media_type)

    top_params = {"limit": 10}
    top_params.update(_media_extra_params(media_type))

    popular_params = {"order_by": "popularity", "sort": "asc", "limit": 10}
    popular_params.update(_media_extra_params(media_type))

    top_anime = _fetch_cached_list(
        f"top:{media_type}",
        f"https://api.jikan.moe/v4/top/{resource}",
        params=top_params,
    )

    if media_type == "anime":
        seasonal_anime = _fetch_cached_list(
            "seasonal:anime",
            "https://api.jikan.moe/v4/seasons/now",
            limit=10,
        )
    else:
        seasonal_anime = []

    popular_anime = _fetch_cached_list(
        f"popular:{media_type}",
        f"https://api.jikan.moe/v4/{resource}",
        params=popular_params,
    )

    return render_template(
        "dashboard.html",
        username=username,
        favorite_ids=favorite_ids,
        top_anime=top_anime,
        seasonal_anime=seasonal_anime,
        popular_anime=popular_anime,
        current_media=media_type,
        media_label=MEDIA_LABELS[media_type],
    )


@main_bp.route("/search", methods=["GET", "POST"])
def search():
    media_type = _get_media_type()
    resource = _api_resource(media_type)
    results = []
    favorite_ids = []

    if request.method == "POST":
        query = (request.form.get("anime_name") or "").strip()
        if query:
            search_params = {"q": query}
            search_params.update(_media_extra_params(media_type))
            results = _fetch_json(
                f"https://api.jikan.moe/v4/{resource}",
                params=search_params,
            ).get("data", [])
            if "user_id" in session:
                favorite_ids = _load_favorite_ids(session["user_id"], media_type)

    return render_template(
        "search.html",
        results=results,
        favorite_ids=favorite_ids,
        current_media=media_type,
        media_label=MEDIA_LABELS[media_type],
    )


@main_bp.route("/anime/<int:anime_id>", methods=["GET", "POST"])
def anime_detail(anime_id):
    media_type = _get_media_type()
    resource = _api_resource(media_type)

    if request.method == "POST" and "user_id" in session:
        selected_status = request.form.get("status")
        if selected_status:
            save_status_db(session["user_id"], anime_id, selected_status, media_type)

    anime = _fetch_json(f"https://api.jikan.moe/v4/{resource}/{anime_id}").get("data")

    is_favorite = False
    my_status = None

    if "user_id" in session:
        connection = get_db_connection()
        is_favorite = (
            connection.execute(
                """
                SELECT 1 FROM favorites
                WHERE user_id = ? AND anime_id = ? AND media_type = ?
                """,
                (session["user_id"], anime_id, media_type),
            ).fetchone()
            is not None
        )
        connection.close()
        my_status = get_status_db(session["user_id"], anime_id, media_type)

    return render_template(
        "anime_detail.html",
        anime=anime,
        is_favorite=is_favorite,
        my_status=my_status,
        current_media=media_type,
        media_label=MEDIA_LABELS[media_type],
    )


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    media_type = _get_media_type()
    user_id = int(session["user_id"])
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == "POST":
        _save_profile_customization(cursor, user_id)
        connection.commit()

    user = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    favorites = get_user_favorites_with_status(user_id)
    grouped_favorites = _build_profile_groups(favorites)
    status_counts = {status: len(grouped_favorites[status]) for status in VALID_STATUS}
    media_counts = {media: 0 for media in PROFILE_MEDIA_ORDER}
    for fav in favorites:
        media_type = (fav["media_type"] or "anime").lower()
        if media_type not in media_counts:
            media_counts[media_type] = 0
        media_counts[media_type] += 1
    total_favorites = len(favorites)
    completion_rate = (
        int((status_counts["Completed"] / total_favorites) * 100)
        if total_favorites
        else 0
    )

    quiz_row = cursor.execute(
        "SELECT COUNT(*) AS total FROM quiz_attempts WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    quiz_count = quiz_row["total"] if quiz_row else 0
    connection.close()

    xp_percentage = (
        int((user["current_xp"] / user["next_level_xp"]) * 100)
        if user["next_level_xp"] > 0
        else 0
    )

    return render_template(
        "profile.html",
        user=user,
        xp_percentage=xp_percentage,
        favorites=favorites,
        grouped_favorites=grouped_favorites,
        status_order=VALID_STATUS,
        status_counts=status_counts,
        media_counts=media_counts,
        media_order=PROFILE_MEDIA_ORDER,
        media_labels=MEDIA_LABELS,
        completion_rate=completion_rate,
        total_favorites=total_favorites,
        quiz_count=quiz_count,
        fav_count=total_favorites,
        badges=[],
        avatar_items=[],
        current_media=media_type,
    )


@main_bp.route("/choose-avatar", methods=["GET", "POST"])
@login_required
def choose_avatar():
    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    avatar_folder = os.path.join("app", "static", "profile_pics")
    available_avatars = os.listdir(avatar_folder)

    if request.method == "POST":
        selected = request.form.get("avatar")
        if selected in available_avatars:
            update_user_avatar(user_id, selected)
        return redirect(url_for("main_bp.profile"))

    return render_template("choose_avatar.html", avatars=available_avatars, user=user)
