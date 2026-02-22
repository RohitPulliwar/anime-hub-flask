from flask import Blueprint

fav_bp=     Blueprint("fav_bp",__name__)

@fav_bp.route("/favorite")
def favorite():
    return "favs"