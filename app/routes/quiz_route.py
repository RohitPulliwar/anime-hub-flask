from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app.routes.auth_route import login_required
from app.db import get_db_connection, add_exp_to_user
import random

quiz_bp = Blueprint("quiz_bp", __name__)

quiz_questions = [
    {
        "question": "Who is Naruto's father?",
        "options": ["Kakashi", "Minato", "Jiraiya", "Itachi"],
        "answer": "Minato"
    },
    {
        "question": "Which anime has Titans?",
        "options": ["Bleach", "One Piece", "Attack on Titan", "Dragon Ball"],
        "answer": "Attack on Titan"
    },
    {
        "question": "Who is Goku's first son?",
        "options": ["Goten", "Vegeta", "Gohan", "Trunks"],
        "answer": "Gohan"
    }
]


@quiz_bp.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():

    
    if request.method == "POST":
        score = 0

        for i, question in enumerate(quiz_questions):
            selected = request.form.get(f"question-{i}")
            if selected == question["answer"]:
                score += 1

        user_id = session["user_id"]
        exp_earned = score * 10

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO quiz_attempts (user_id, score, exp_earned) VALUES (?, ?, ?)",
            (user_id, score, exp_earned)
        )
        conn.commit()
        conn.close()

        # update user XP
        add_exp_to_user(user_id, exp_earned)

        flash(f"You scored {score}/{len(quiz_questions)}! +{exp_earned} XP")

        return redirect(url_for("main_bp.profile"))

    
    random.shuffle(quiz_questions)

    return render_template("quiz.html", questions=quiz_questions)