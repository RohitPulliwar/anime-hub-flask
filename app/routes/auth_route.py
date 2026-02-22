from flask import Blueprint,render_template, request, redirect,flash,session,url_for
import sqlite3
from werkzeug.security import check_password_hash,generate_password_hash
from functools import wraps
auth_bp= Blueprint("auth_bp",__name__)

@auth_bp.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        username=request.form["username"]
        password=request.form["password"]

        hashed_pass= generate_password_hash(password)

        conn=sqlite3.connect("database.db")
        cursor=conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username , password) VALUES (?,?)", (username , hashed_pass)

            )
            conn.commit()
            flash("REGISTRATION completed")
            return redirect("/login")
        except:
            flash("USER ALREADY EXISTS")
            

        finally:
            conn.close()
    return render_template("register.html")


@auth_bp.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
           
        username=request.form["username"]
        password=request.form["password"]

        conn= sqlite3.connect("database.db")
        cursor=conn.cursor()

        cursor.execute(
            "SELECT id , password FROM users WHERE username=?", (username,)
                          )
        user= cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[1],password):
            session["user_id"]= user[0]
            flash("login successful")
            return redirect("/dashboard")
        else:
            flash("incorrect data")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    if "user_id" in session:
        session.pop("user_id",None)
        flash("logged out successfully")
    return redirect(url_for("main_bp.home"))


def login_required(f):
    @wraps(f)
    def wrapper(*args ,**kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth_bp.login"))
        return f(*args, **kwargs)
    return wrapper