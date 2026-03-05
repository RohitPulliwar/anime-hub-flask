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


def _get_media_type():
    media_type = (request.args.get("media") or "anime").strip().lower()
    return media_type if media_type in MEDIA_LABELS else "anime"


def _get_difficulty():
    difficulty = (request.args.get("difficulty") or "all").strip().lower()
    return difficulty if difficulty in VALID_DIFFICULTIES else "all"


def _fetch_quiz_questions(media_type, difficulty="all", limit=QUESTIONS_PER_QUIZ):
    connection = get_db_connection()

    if difficulty == "all":
        rows = connection.execute(
            """
            SELECT id, question_text, difficulty
            FROM quiz_questions
            WHERE is_active = 1 AND media_type = ?
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (media_type, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT id, question_text, difficulty
            FROM quiz_questions
            WHERE is_active = 1 AND media_type = ? AND difficulty = ?
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (media_type, difficulty, limit),
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

    if request.method == "GET":
        questions = _fetch_quiz_questions(media_type, difficulty=difficulty, limit=QUESTIONS_PER_QUIZ)
        session["quiz_question_ids"] = [question["id"] for question in questions]
        session["quiz_media_type"] = media_type
        session["quiz_difficulty"] = difficulty

        if not questions:
            if difficulty == "all":
                flash(f"No {MEDIA_LABELS.get(media_type, 'selected')} quiz questions available yet.")
            else:
                flash(
                    f"No {difficulty.title()} {MEDIA_LABELS.get(media_type, 'selected')} "
                    "quiz questions available yet."
                )
            return redirect(url_for("main_bp.profile", media=media_type))

        return render_template(
            "quiz.html",
            questions=questions,
            media_label=MEDIA_LABELS.get(media_type, "Anime"),
            current_media=media_type,
            media_switch_endpoint="quiz_bp.quiz",
            media_switch_difficulty=difficulty,
            current_difficulty=difficulty,
        )

    question_ids = session.get("quiz_question_ids", [])
    quiz_media_type = session.get("quiz_media_type", "anime")

    if not question_ids:
        flash("Quiz session expired. Please start again.")
        return redirect(url_for("quiz_bp.quiz", media=media_type))

    score = _calculate_quiz_score(question_ids, request.form)
    exp_earned = score * 10
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

    flash(
        f"{MEDIA_LABELS.get(quiz_media_type, 'Anime')} quiz complete: "
        f"{score}/{total_questions} correct (+{exp_earned} XP)."
    )
    return redirect(url_for("main_bp.profile", media=quiz_media_type))
