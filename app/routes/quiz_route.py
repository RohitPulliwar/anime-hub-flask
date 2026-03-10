from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.db import add_exp_to_user, get_db_connection
from app.routes.auth_route import login_required

quiz_bp = Blueprint("quiz_bp", __name__)

MEDIA_LABELS = {
    "anime": "Anime",
    "manga": "Manga",
    "lightnovel": "Light Novel",
}
VALID_DIFFICULTIES = {"all", "easy", "medium", "hard"}
QUESTIONS_PER_QUIZ = 5
XP_PER_CORRECT_BY_DIFFICULTY = {
    "all": 50,
    "easy": 10,
    "medium": 20,
    "hard": 35,
}
SERIES_LABELS = {
    "one_piece": "One Piece",
    "dragon_ball": "Dragon Ball",
    "naruto": "Naruto",
    "bleach": "Bleach",
}


def _get_media_type():
    media_type = (request.args.get("media") or "anime").strip().lower()
    return media_type if media_type in MEDIA_LABELS else "anime"


def _get_difficulty():
    difficulty = (request.args.get("difficulty") or "all").strip().lower()
    return difficulty if difficulty in VALID_DIFFICULTIES else "all"


def _series_label(series_tag):
    return SERIES_LABELS.get(series_tag, series_tag.replace("_", " ").title())


def _available_quiz_series(media_type):
    connection = get_db_connection()
    rows = connection.execute(
        """
        SELECT DISTINCT quiz_tag
        FROM quiz_questions
        WHERE is_active = 1 AND media_type = ? AND quiz_tag IS NOT NULL AND quiz_tag != ''
        ORDER BY quiz_tag ASC
        """,
        (media_type,),
    ).fetchall()
    connection.close()
    return [row["quiz_tag"] for row in rows]


def _fetch_quiz_questions(media_type, difficulty="all", quiz_tag="all", limit=QUESTIONS_PER_QUIZ):
    connection = get_db_connection()

    filters = ["is_active = 1", "media_type = ?"]
    params = [media_type]
    if difficulty != "all":
        filters.append("difficulty = ?")
        params.append(difficulty)
    if quiz_tag != "all":
        filters.append("quiz_tag = ?")
        params.append(quiz_tag)

    rows = connection.execute(
        f"""
        SELECT id, question_text, difficulty, quiz_tag
        FROM quiz_questions
        WHERE {' AND '.join(filters)}
        ORDER BY RANDOM()
        LIMIT ?
        """,
        tuple(params + [limit]),
    ).fetchall()

    question_ids = [row["id"] for row in rows]
    options_by_question = {qid: [] for qid in question_ids}

    if question_ids:
        placeholders = ",".join("?" for _ in question_ids)
        option_rows = connection.execute(
            f"""
            SELECT id, question_id, option_text
            FROM quiz_options
            WHERE question_id IN ({placeholders})
            ORDER BY RANDOM()
            """,
            question_ids,
        ).fetchall()

        for option in option_rows:
            options_by_question[option["question_id"]].append(
                {"id": option["id"], "text": option["option_text"]}
            )

    connection.close()

    questions = []
    for row in rows:
        questions.append(
            {
                "id": row["id"],
                "question": row["question_text"],
                "difficulty": row["difficulty"],
                "quiz_tag": row["quiz_tag"],
                "options": options_by_question.get(row["id"], []),
            }
        )
    return questions


def _calculate_quiz_score(question_ids, form_data):
    if not question_ids:
        return 0

    connection = get_db_connection()
    score = 0

    for question_id in question_ids:
        selected = form_data.get(f"question-{question_id}")
        if not selected:
            continue

        correct = connection.execute(
            """
            SELECT id FROM quiz_options
            WHERE question_id = ? AND is_correct = 1
            LIMIT 1
            """,
            (question_id,),
        ).fetchone()

        if correct and int(selected) == correct["id"]:
            score += 1

    connection.close()
    return score


@quiz_bp.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    media_type = _get_media_type()
    difficulty = _get_difficulty()
    available_series = _available_quiz_series(media_type)
    selected_series = (request.args.get("series") or "").strip().lower()
    if selected_series and selected_series not in available_series:
        selected_series = ""

    if request.method == "GET":
        if not available_series:
            flash(f"No {MEDIA_LABELS.get(media_type, 'selected')} quiz questions available yet.")
            return redirect(url_for("main_bp.profile", media=media_type))

        if not selected_series:
            return render_template(
                "quiz.html",
                questions=[],
                media_label=MEDIA_LABELS.get(media_type, "Anime"),
                current_media=media_type,
                media_switch_endpoint="quiz_bp.quiz",
                media_switch_difficulty=difficulty,
                current_difficulty=difficulty,
                series_options=available_series,
                current_series="",
                series_label_map=SERIES_LABELS,
                choose_series_only=True,
            )

        questions = _fetch_quiz_questions(
            media_type,
            difficulty=difficulty,
            quiz_tag=selected_series,
            limit=QUESTIONS_PER_QUIZ,
        )
        session["quiz_question_ids"] = [question["id"] for question in questions]
        session["quiz_media_type"] = media_type
        session["quiz_difficulty"] = difficulty
        session["quiz_series"] = selected_series

        if not questions:
            detail = [_series_label(selected_series)]
            if difficulty != "all":
                detail.append(difficulty.title())
            detail_text = " ".join(detail).strip()
            if detail_text:
                flash(
                    f"No {detail_text} {MEDIA_LABELS.get(media_type, 'selected')} quiz questions available yet."
                )
            else:
                flash(f"No {MEDIA_LABELS.get(media_type, 'selected')} quiz questions available yet.")
            return redirect(url_for("main_bp.profile", media=media_type))

        return render_template(
            "quiz.html",
            questions=questions,
            media_label=MEDIA_LABELS.get(media_type, "Anime"),
            current_media=media_type,
            media_switch_endpoint="quiz_bp.quiz",
            media_switch_difficulty=difficulty,
            media_switch_series=selected_series,
            current_difficulty=difficulty,
            series_options=available_series,
            current_series=selected_series,
            series_label_map=SERIES_LABELS,
            choose_series_only=False,
        )

    question_ids = session.get("quiz_question_ids", [])
    quiz_media_type = session.get("quiz_media_type", "anime")
    quiz_difficulty = session.get("quiz_difficulty", "all")

    if not question_ids:
        flash("Quiz session expired. Please start again.")
        return redirect(url_for("quiz_bp.quiz", media=media_type))

    score = _calculate_quiz_score(question_ids, request.form)
    xp_per_correct = XP_PER_CORRECT_BY_DIFFICULTY.get(quiz_difficulty, 10)
    exp_earned = score * xp_per_correct
    user_id = session["user_id"]

    connection = get_db_connection()
    connection.execute(
        """
        INSERT INTO quiz_attempts (user_id, score, exp_earned, media_type)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, score, exp_earned, quiz_media_type),
    )
    connection.commit()
    connection.close()

    add_exp_to_user(user_id, exp_earned)
    total_questions = len(question_ids)

    session.pop("quiz_question_ids", None)
    session.pop("quiz_media_type", None)
    session.pop("quiz_difficulty", None)
    session.pop("quiz_series", None)

    flash(
        f"{MEDIA_LABELS.get(quiz_media_type, 'Anime')} quiz complete: "
        f"{score}/{total_questions} correct (+{exp_earned} XP)."
    )
    return redirect(url_for("main_bp.profile", media=quiz_media_type))
