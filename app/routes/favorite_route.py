from flask import Blueprint, session, request, jsonify
from app.routes.auth_route import login_required
from app.db import add_favorite_db, remove_favorite_db, check_favorite

fav_bp = Blueprint("fav_bp", __name__)

@fav_bp.route("/toggle_favorite", methods=["POST"])
@login_required
def toggle_favorite():

    user_id = session.get("user_id")

    data = request.get_json()
    anime_id = int(data.get("anime_id"))
    anime_title = data.get("anime_title")
    anime_image = data.get("anime_image")

    if check_favorite(user_id, anime_id):
        remove_favorite_db(user_id, anime_id)
        return jsonify({"status": "removed"})
    else:
        add_favorite_db(user_id, anime_id, anime_title, anime_image)
        return jsonify({"status": "added"})
