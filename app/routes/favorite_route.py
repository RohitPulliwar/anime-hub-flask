from flask import Blueprint, jsonify, request, session

from app.db import add_favorite_db, check_favorite, remove_favorite_db
from app.routes.auth_route import login_required

fav_bp = Blueprint("fav_bp", __name__)

VALID_MEDIA_TYPES = {"anime", "manga", "lightnovel"}


@fav_bp.route("/toggle_favorite", methods=["POST"])
@login_required
def toggle_favorite():
    payload = request.get_json(silent=True) or {}

    anime_id = payload.get("anime_id")
    anime_title = (payload.get("anime_title") or "").strip()
    anime_image = (payload.get("anime_image") or "").strip()
    media_type = (payload.get("media_type") or "anime").strip().lower()
    user_id = session.get("user_id")

    if media_type not in VALID_MEDIA_TYPES:
        return jsonify({"status": "error", "message": "Invalid media type"}), 400

    if not anime_id or not anime_title or not anime_image:
        return jsonify({"status": "error", "message": "Missing anime payload"}), 400

    anime_id = int(anime_id)

    if check_favorite(user_id, anime_id, media_type):
        remove_favorite_db(user_id, anime_id, media_type)
        return jsonify({"status": "removed"})

    add_favorite_db(user_id, anime_id, anime_title, anime_image, media_type)
    return jsonify({"status": "added"})
