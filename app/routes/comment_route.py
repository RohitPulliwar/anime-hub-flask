from flask import Blueprint, flash, redirect, request, session, url_for

from app.db import add_comment_db
from app.routes.auth_route import login_required


comment_bp = Blueprint("comment_bp", __name__)
VALID_MEDIA_TYPES = {"anime", "manga", "lightnovel"}


@comment_bp.route("/add_comment", methods=["POST"])
@login_required
def add_comment():
    anime_id_raw = (request.form.get("anime_id") or "").strip()
    content = (request.form.get("content") or "").strip()
    media_type = (request.form.get("media_type") or "anime").strip().lower()

    if not anime_id_raw.isdigit():
        flash("Invalid anime id.")
        return redirect(url_for("main_bp.home"))

    if media_type not in VALID_MEDIA_TYPES:
        media_type = "anime"

    anime_id = int(anime_id_raw)

    if not content:
        flash("Comment cannot be empty.")
        return redirect(url_for("main_bp.anime_detail", anime_id=anime_id, media=media_type))

    add_comment_db(session["user_id"], anime_id, content, media_type)
    flash("Comment added.")
    return redirect(url_for("main_bp.anime_detail", anime_id=anime_id, media=media_type))
