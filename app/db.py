import sqlite3

DATABASE = "database.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


#  USERS 
def create_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (username, password)
    )

    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE username=?",
        (username,)
    )

    user = cursor.fetchone()
    conn.close()
    return user




# FAVORITES 

def add_favorite_db(user_id, anime_id, title, image):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO favorites (user_id, anime_id, anime_title, anime_image) VALUES (?, ?, ?, ?)",
        (user_id, anime_id, title, image)
    )

    conn.commit()
    conn.close()


def remove_favorite_db(user_id, anime_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM favorites WHERE user_id=? AND anime_id=?",
        (user_id, anime_id)
    )

    conn.commit()
    conn.close()


def get_user_favorites(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM favorites WHERE user_id=?",
        (user_id,)
    )

    favorites = cursor.fetchall()
    conn.close()
    return favorites


def check_favorite(user_id, anime_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM favorites WHERE user_id=? AND anime_id=?",
        (user_id, anime_id)
    )

    result = cursor.fetchone()
    conn.close()

    return result is not None

def add_exp_to_user(user_id, exp_gain):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT exp, level FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()

    if user:
        current_exp, current_level = user
        new_exp = current_exp + exp_gain

        while new_exp >= 100:
            new_exp -= 100
            current_level += 1

        cursor.execute(
            "UPDATE users SET exp=?, level=? WHERE id=?",
            (new_exp, current_level, user_id)
        )
        conn.commit()

    conn.close()


def get_user_level_info(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT exp, level FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()

    conn.close()

    if user:
        return {"exp": user[0], "level": user[1]}
    return {"exp": 0, "level": 1}

def update_user_avatar(user_id, avatar_filename):
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET avatar=? WHERE id=?",
        (avatar_filename, user_id)
    )
    conn.commit()
    conn.close()


def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    return user