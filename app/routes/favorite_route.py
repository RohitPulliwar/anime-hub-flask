from flask import Blueprint, jsonify, request, session

from app.db import add_favorite_db, check_favorite, remove_favorite_db
from app.routes.auth_route import login_required

fav_bp = Blueprint("fav_bp", __name__)


@fav_bp.route("/toggle_favorite", methods=["POST"])
@login_required
def toggle_favorite():
    payload = request.get_json(silent=True) or {}

    anime_id = payload.get("anime_id")
    anime_title = (payload.get("anime_title") or "").strip()
    anime_image = (payload.get("anime_image") or "").strip()
    user_id = session.get("user_id")

    if not anime_id or not anime_title or not anime_image:
        return jsonify({"status": "error", "message": "Missing anime payload"}), 400

    anime_id = int(anime_id)

    if check_favorite(user_id, anime_id):
        remove_favorite_db(user_id, anime_id)
        return jsonify({"status": "removed"})

    add_favorite_db(user_id, anime_id, anime_title, anime_image)
    return jsonify({"status": "added"})
