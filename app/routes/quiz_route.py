import random

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.db import add_exp_to_user, get_db_connection
from app.routes.auth_route import login_required

quiz_bp = Blueprint("quiz_bp", __name__)

QUIZ_BANK = [
    {
        "question": "Who is Naruto's father?",
        "options": ["Kakashi", "Minato", "Jiraiya", "Itachi"],
        "answer": "Minato",
    },
    {
        "question": "Which anime has Titans?",
        "options": ["Bleach", "One Piece", "Attack on Titan", "Dragon Ball"],
        "answer": "Attack on Titan",
    },
    {
        "question": "Who is Goku's first son?",
        "options": ["Goten", "Vegeta", "Gohan", "Trunks"],
        "answer": "Gohan",
    },
]


def _calculate_quiz_score(form_data):
    score = 0
    for idx, prompt in enumerate(QUIZ_BANK):
        if form_data.get(f"question-{idx}") == prompt["answer"]:
            score += 1
    return score


@quiz_bp.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    if request.method == "GET":
        random.shuffle(QUIZ_BANK)
        return render_template("quiz.html", questions=QUIZ_BANK)

    score = _calculate_quiz_score(request.form)
    exp_earned = score * 10
    user_id = session["user_id"]

    connection = get_db_connection()
    connection.execute(
        """
        INSERT INTO quiz_attempts (user_id, score, exp_earned)
        VALUES (?, ?, ?)
        """,
        (user_id, score, exp_earned),
    )
    connection.commit()
    connection.close()

    add_exp_to_user(user_id, exp_earned)

    flash(f"Quiz complete: {score}/{len(QUIZ_BANK)} correct (+{exp_earned} XP).")
    return redirect(url_for("main_bp.profile"))
