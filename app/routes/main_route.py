import os
import re
import time
from html import unescape
from urllib.parse import urlparse
from uuid import uuid4

import requests
from requests import RequestException
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
    get_comments_for_anime,
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
API_TIMEOUT_SECONDS = 8
API_MAX_RETRIES = 2
API_INITIAL_BACKOFF_SECONDS = 0.75
API_MAX_RETRY_AFTER_SECONDS = 2
API_MAX_TOTAL_WAIT_SECONDS = 8
ANILIST_API_URL = "https://graphql.anilist.co"
DEFAULT_COVER_IMAGE = "https://dummyimage.com/600x900/0f2533/eaf8ff.png&text=No+Cover"
VALID_STATUS = ["Watching", "Completed", "Plan to Watch", "Dropped", "Not Set"]
DEFAULT_THEME = "#40e0d0"
MEDIA_LABELS = {
    "anime": "Anime",
    "manga": "Manga",
    "lightnovel": "Light Novel",
}
PROFILE_MEDIA_ORDER = ["anime", "manga", "lightnovel"]
OFFLINE_CARDS = {
    "anime": [
        {"id": 16498, "title": "Attack on Titan", "averageScore": 90},
        {"id": 5114, "title": "Fullmetal Alchemist: Brotherhood", "averageScore": 91},
        {"id": 9253, "title": "Steins;Gate", "averageScore": 90},
        {"id": 1535, "title": "Death Note", "averageScore": 86},
        {"id": 11061, "title": "Hunter x Hunter (2011)", "averageScore": 90},
        {"id": 21, "title": "One Piece", "averageScore": 87},
        {"id": 40748, "title": "Jujutsu Kaisen", "averageScore": 86},
        {"id": 38000, "title": "Demon Slayer", "averageScore": 85},
        {"id": 35849, "title": "Rascal Does Not Dream", "averageScore": 82},
        {"id": 31240, "title": "Re:Zero", "averageScore": 83},
    ],
    "manga": [
        {"id": 2, "title": "Berserk", "averageScore": 94},
        {"id": 13, "title": "One Piece", "averageScore": 92},
        {"id": 656, "title": "Vagabond", "averageScore": 93},
        {"id": 1, "title": "Monster", "averageScore": 91},
        {"id": 16765, "title": "Kingdom", "averageScore": 90},
        {"id": 51, "title": "Slam Dunk", "averageScore": 89},
        {"id": 33327, "title": "Tokyo Ghoul", "averageScore": 84},
    ],
    "lightnovel": [
        {"id": 11992, "title": "Overlord", "averageScore": 87},
        {"id": 31240, "title": "Re:Zero", "averageScore": 86},
        {"id": 19815, "title": "No Game No Life", "averageScore": 83},
        {"id": 35507, "title": "Classroom of the Elite", "averageScore": 82},
        {"id": 39535, "title": "Mushoku Tensei", "averageScore": 88},
        {"id": 37430, "title": "That Time I Got Reincarnated as a Slime", "averageScore": 81},
        {"id": 28121, "title": "DanMachi", "averageScore": 79},
    ],
}


def _offline_trending(media_type):
    cards = []
    for item in OFFLINE_CARDS.get(media_type, OFFLINE_CARDS["anime"]):
        cards.append(
            {
                "id": item["id"],
                "title": item["title"],
                "averageScore": item["averageScore"],
                "episodes": None,
                "chapters": None,
                "status": None,
                "format": None,
                "description": None,
                "genres": [],
                "coverImage": {
                    "extraLarge": DEFAULT_COVER_IMAGE,
                    "large": DEFAULT_COVER_IMAGE,
                    "medium": DEFAULT_COVER_IMAGE,
                },
            }
        )
    return cards[:12]


def _favorite_cards_fallback(media_type, limit=12):
    connection = get_db_connection()
    rows = connection.execute(
        """
        SELECT anime_id, anime_title, anime_image, MAX(id) AS latest_id
        FROM favorites
        WHERE media_type = ? AND anime_image IS NOT NULL AND anime_image != ''
        GROUP BY anime_id, anime_title, anime_image
        ORDER BY latest_id DESC
        LIMIT ?
        """,
        (media_type, limit),
    ).fetchall()
    connection.close()

    cards = []
    for row in rows:
        image_url = row["anime_image"] or DEFAULT_COVER_IMAGE
        cards.append(
            {
                "id": row["anime_id"],
                "title": row["anime_title"] or "Untitled",
                "averageScore": None,
                "episodes": None,
                "chapters": None,
                "status": None,
                "format": None,
                "description": None,
                "genres": [],
                "coverImage": {
                    "extraLarge": image_url,
                    "large": image_url,
                    "medium": image_url,
                },
            }
        )
    return cards


def _best_available_cards(media_type, cards, limit=12):
    if cards:
        return cards[:limit], None

    favorite_cards = _favorite_cards_fallback(media_type, limit=limit)
    if favorite_cards:
        return favorite_cards, "favorites"

    return _offline_trending(media_type)[:limit], "offline"


def _sort_by_score_desc(items):
    return sorted(
        items or [],
        key=lambda item: (item.get("averageScore") is not None, item.get("averageScore") or -1),
        reverse=True,
    )


def _get_media_type():
    media_type = (request.args.get("media") or "anime").strip().lower()
    return media_type if media_type in MEDIA_LABELS else "anime"


def _fetch_anilist(query, variables=None):
    started_at = time.time()
    backoff_seconds = API_INITIAL_BACKOFF_SECONDS
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "self-flask-anilist-client/1.0",
    }

    for attempt in range(API_MAX_RETRIES):
        if time.time() - started_at > API_MAX_TOTAL_WAIT_SECONDS:
            raise RequestException("AniList request timed out by retry budget.")

        try:
            response = requests.post(
                ANILIST_API_URL,
                json={"query": query, "variables": variables or {}},
                headers=headers,
                timeout=API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RequestException("AniList GraphQL returned errors.")
            return payload
        except requests.HTTPError as err:
            status_code = err.response.status_code if err.response is not None else None
            retryable_status = {429, 500, 502, 503, 504}
            if status_code not in retryable_status or attempt == API_MAX_RETRIES - 1:
                raise
            retry_after = (err.response.headers or {}).get("Retry-After") if err.response is not None else None
            if retry_after and retry_after.isdigit():
                time.sleep(min(int(retry_after), API_MAX_RETRY_AFTER_SECONDS))
                backoff_seconds *= 2
                continue
        except RequestException:
            if attempt == API_MAX_RETRIES - 1:
                raise

        time.sleep(backoff_seconds)
        backoff_seconds *= 2


def _fetch_cached_list(cache_key, fetcher, limit=None):
    now = time.time()
    full_cache_key = f"{cache_key}:{limit}"
    cached = API_CACHE.get(full_cache_key)

    if cached and now - cached["at"] < CACHE_TTL_SECONDS:
        data = cached["payload"]
    else:
        try:
            data = fetcher()
            API_CACHE[full_cache_key] = {"payload": data, "at": now}
        except RequestException:
            data = cached["payload"] if cached else []

    return data[:limit] if limit else data


def _anilist_media_type(media_type):
    return "ANIME" if media_type == "anime" else "MANGA"


def _anilist_format_filters(media_type):
    if media_type == "lightnovel":
        return ["NOVEL"], []
    return [], []


def _humanize_enum(value):
    if not value:
        return None
    return value.replace("_", " ").title()


def _clean_description(text):
    if not text:
        return None
    no_tags = re.sub(r"<[^>]+>", "", text)
    cleaned = no_tags.replace("~!", "").replace("!~", "")
    return unescape(cleaned).strip()


def _normalize_anilist_item(item):
    if not item:
        return None

    title_obj = item.get("title") or {}
    title = title_obj.get("english") or title_obj.get("romaji") or title_obj.get("native") or "Untitled"
    cover_obj = item.get("coverImage") or {}
    image_url = (
        cover_obj.get("extraLarge")
        or cover_obj.get("large")
        or cover_obj.get("medium")
        or DEFAULT_COVER_IMAGE
    )

    return {
        "id": item.get("id"),
        "title": title,
        "averageScore": item.get("averageScore"),
        "episodes": item.get("episodes"),
        "chapters": item.get("chapters"),
        "status": _humanize_enum(item.get("status")),
        "format": _humanize_enum(item.get("format")),
        "description": _clean_description(item.get("description")),
        "genres": item.get("genres") or [],
        "coverImage": {
            "extraLarge": cover_obj.get("extraLarge") or image_url,
            "large": image_url,
            "medium": cover_obj.get("medium") or image_url,
        },
    }


def _current_anime_season():
    month = time.gmtime().tm_mon
    year = time.gmtime().tm_year
    if month in {12, 1, 2}:
        return "WINTER", year
    if month in {3, 4, 5}:
        return "SPRING", year
    if month in {6, 7, 8}:
        return "SUMMER", year
    return "FALL", year


def _fetch_anilist_media_list(media_type, per_page=12, sort="popularity", top=False, seasonal=False, search=None):
    sort_map = {
        "popularity": ["POPULARITY_DESC"],
        "score": ["SCORE_DESC"],
    }
    media_type_value = _anilist_media_type(media_type)
    format_in, format_not_in = _anilist_format_filters(media_type)
    if top:
        sort_value = ["SCORE_DESC", "POPULARITY_DESC"]
    elif search:
        sort_value = ["POPULARITY_DESC"]
    else:
        sort_value = sort_map.get(sort, ["POPULARITY_DESC"])

    variables = {"page": 1, "perPage": per_page, "type": media_type_value, "sort": sort_value}
    var_defs = ["$page: Int", "$perPage: Int", "$type: MediaType", "$sort: [MediaSort]"]
    media_args = ["type: $type", "sort: $sort", "isAdult: false"]

    if search:
        variables["search"] = search
        var_defs.append("$search: String")
        media_args.append("search: $search")

    if seasonal and media_type == "anime":
        season, season_year = _current_anime_season()
        variables["season"] = season
        variables["seasonYear"] = season_year
        var_defs.append("$season: MediaSeason")
        var_defs.append("$seasonYear: Int")
        media_args.append("season: $season")
        media_args.append("seasonYear: $seasonYear")

    use_format_filters = bool(format_in or format_not_in)
    if use_format_filters:
        variables["formatIn"] = format_in
        variables["formatNotIn"] = format_not_in
        var_defs.extend(["$formatIn: [MediaFormat]", "$formatNotIn: [MediaFormat]"])
        media_args.extend(["format_in: $formatIn", "format_not_in: $formatNotIn"])

    query = f"""
    query ({", ".join(var_defs)}) {{
      Page(page: $page, perPage: $perPage) {{
        media({", ".join(media_args)}) {{
          id
          title {{
            romaji
            english
            native
          }}
          coverImage {{
            extraLarge
            large
            medium
          }}
          averageScore
          episodes
          chapters
          status
          format
          description(asHtml: false)
          genres
        }}
      }}
    }}
    """

    # Fallback to a lighter query when AniList intermittently fails.
    light_query = f"""
    query ({", ".join(var_defs)}) {{
      Page(page: $page, perPage: $perPage) {{
        media({", ".join(media_args)}) {{
          id
          title {{
            romaji
            english
            native
          }}
          coverImage {{
            extraLarge
            large
            medium
          }}
          averageScore
          episodes
          chapters
          status
          format
        }}
      }}
    }}
    """

    try:
        payload = _fetch_anilist(query, variables=variables)
    except RequestException:
        payload = _fetch_anilist(light_query, variables=variables)
    raw = ((payload.get("data") or {}).get("Page") or {}).get("media") or []
    items = [_normalize_anilist_item(item) for item in raw if item]
    if top:
        items.sort(key=lambda item: (item.get("averageScore") is not None, item.get("averageScore") or -1), reverse=True)
    return items


def _fetch_anilist_media_detail(media_id, media_type):
    query = """
    query ($id: Int, $type: MediaType) {
      Media(id: $id, type: $type, isAdult: false) {
        id
        title {
          romaji
          english
          native
        }
        coverImage {
          extraLarge
          large
          medium
        }
        averageScore
        episodes
        chapters
        status
        format
        description(asHtml: false)
        genres
      }
    }
    """

    payload = _fetch_anilist(
        query,
        variables={"id": media_id, "type": _anilist_media_type(media_type)},
    )
    media = (payload.get("data") or {}).get("Media")
    return _normalize_anilist_item(media) if media else None


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
    trending = _fetch_cached_list(
        f"anilist_trending_v1:{media_type}",
        lambda: _fetch_anilist_media_list(
            media_type,
            per_page=12,
            sort="popularity",
        ),
    )
    trending = _sort_by_score_desc(trending)

    trending, source = _best_available_cards(media_type, trending, limit=12)
    if source == "favorites":
        flash(
            f"Live {MEDIA_LABELS[media_type]} feed is temporarily unavailable. "
            "Showing your recent favorites."
        )
    elif source == "offline":
        flash(
            f"Live {MEDIA_LABELS[media_type]} feed is temporarily unavailable. "
            "Showing offline cards."
        )

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
    username = session.get("username")
    favorite_ids = _load_favorite_ids(session["user_id"], media_type)

    top_anime = _fetch_cached_list(
        f"anilist_top_v1:{media_type}",
        lambda: _fetch_anilist_media_list(
            media_type,
            per_page=10,
            top=True,
        ),
    )
    top_anime = _sort_by_score_desc(top_anime)
    top_anime, top_source = _best_available_cards(media_type, top_anime, limit=10)

    if media_type == "anime":
        seasonal_anime = _fetch_cached_list(
            "anilist_seasonal_v1:anime",
            lambda: _fetch_anilist_media_list(
                media_type,
                per_page=10,
                seasonal=True,
            ),
        )
        seasonal_anime, seasonal_source = _best_available_cards(media_type, seasonal_anime, limit=10)
    else:
        seasonal_anime = []
        seasonal_source = None

    popular_anime = _fetch_cached_list(
        f"anilist_popular_v1:{media_type}",
        lambda: _fetch_anilist_media_list(
            media_type,
            per_page=10,
            sort="popularity",
        ),
    )
    popular_anime = _sort_by_score_desc(popular_anime)
    popular_anime, popular_source = _best_available_cards(media_type, popular_anime, limit=10)

    if "offline" in {top_source, seasonal_source, popular_source}:
        flash(
            f"Some live {MEDIA_LABELS[media_type]} sections are temporarily unavailable. "
            "Showing offline cards where needed."
        )
    elif "favorites" in {top_source, seasonal_source, popular_source}:
        flash(
            f"Some live {MEDIA_LABELS[media_type]} sections are temporarily unavailable. "
            "Showing your recent favorites where needed."
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
    results = []
    favorite_ids = []

    if request.method == "POST":
        query = (request.form.get("anime_name") or "").strip()
        if query:
            try:
                results = _fetch_anilist_media_list(
                    media_type,
                    per_page=20,
                    search=query,
                )
                results = _sort_by_score_desc(results)
            except RequestException:
                flash("Search is temporarily unavailable. Please try again.")
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
    fallback_back_url = url_for("main_bp.home", media=media_type)
    session_back_key = f"detail_back_url:{media_type}:{anime_id}"
    back_url = session.get(session_back_key) or fallback_back_url
    referrer = request.referrer or ""
    blocked_back_paths = {url_for("comment_bp.add_comment"), url_for("fav_bp.toggle_favorite")}
    if referrer:
        parsed_referrer = urlparse(referrer)
        is_same_detail_path = parsed_referrer.path == request.path
        if (
            parsed_referrer.path
            and parsed_referrer.path not in blocked_back_paths
            and not is_same_detail_path
        ):
            back_url = referrer
            session[session_back_key] = back_url

    if request.method == "POST" and "user_id" in session:
        selected_status = request.form.get("status")
        if selected_status:
            save_status_db(session["user_id"], anime_id, selected_status, media_type)

    try:
        anime = _fetch_anilist_media_detail(anime_id, media_type)
        if not anime:
            flash("Could not find this title.")
            return redirect(url_for("main_bp.home", media=media_type))
    except RequestException:
        flash("Details are temporarily unavailable. Please try again.")
        return redirect(url_for("main_bp.home", media=media_type))

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

    comments = get_comments_for_anime(anime_id, media_type)

    return render_template(
        "anime_detail.html",
        anime=anime,
        is_favorite=is_favorite,
        my_status=my_status,
        comments=comments,
        back_url=back_url,
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
