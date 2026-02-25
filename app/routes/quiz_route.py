from flask import Blueprint,session,Flask,request,flash,redirect,render_template
from app.routes.auth_route import login_required
quiz_bp=Blueprint("quiz_bp",__name__)
from app.routes.main_route import quiz_questions
from app.db import get_db_connection,get_user_by_username,get_user_level_info,add_exp_to_user
@quiz_bp.route("/quiz",methods=["GET","POST"])
@login_required
def quiz():
    if request.method=="POST":
        score=0

        for i,j in enumerate(quiz_questions):
            selected=request.form.get(f"quesriion-{i}")
            if selected==j["answer"]:
                score+=1

        exp_gain=score*20
        add_exp_to_user(session["user_id"],exp_gain)

        conn=get_db_connection()
        conn.execute(
            "INSERT INTO quiz_attempts (user_id, score, exp_earned) VALUES (?, ?, ?)",
            (session["user_id"], score, exp_gain)
        )
        conn.commit()
        conn.close
        return render_template("quiz.html",questions=quiz_questions)

