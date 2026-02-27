import sqlite3

DATABASE = "database.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        current_xp INTEGER DEFAULT 0,
        next_level_xp INTEGER DEFAULT 100,
        level INTEGER DEFAULT 1,
        avatar TEXT DEFAULT 'default.png'
    );
    """)

    # Backfill new profile customization columns for existing databases.
    existing_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    if "bio" not in existing_columns:
        conn.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
    if "banner_url" not in existing_columns:
        conn.execute("ALTER TABLE users ADD COLUMN banner_url TEXT DEFAULT ''")
    if "theme_color" not in existing_columns:
        conn.execute("ALTER TABLE users ADD COLUMN theme_color TEXT DEFAULT '#40e0d0'")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        anime_id INTEGER NOT NULL,
        anime_title TEXT NOT NULL,
        anime_image TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        score INTEGER DEFAULT 0,
        exp_earned INTEGER DEFAULT 0,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)

    conn.execute("""
CREATE TABLE IF NOT EXISTS user_anime_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    anime_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
""")

    conn.commit()
    conn.close()


# ---------------- USERS ---------------- #

def create_user(username, password):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (username, password)
    )
    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username=?",
        (username,)
    ).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    return user


# ---------------- FAVORITES ---------------- #

def add_favorite_db(user_id, anime_id, title, image):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO favorites (user_id, anime_id, anime_title, anime_image) VALUES (?, ?, ?, ?)",
        (user_id, anime_id, title, image)
    )
    conn.commit()
    conn.close()


def remove_favorite_db(user_id, anime_id):
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM favorites WHERE user_id=? AND anime_id=?",
        (user_id, anime_id)
    )
    conn.commit()
    conn.close()


def get_user_favorites(user_id):
    conn = get_db_connection()
    favorites = conn.execute(
        "SELECT * FROM favorites WHERE user_id=?",
        (user_id,)
    ).fetchall()
    conn.close()
    return favorites


def check_favorite(user_id, anime_id):
    conn = get_db_connection()
    result = conn.execute(
        "SELECT 1 FROM favorites WHERE user_id=? AND anime_id=?",
        (user_id, anime_id)
    ).fetchone()
    conn.close()
    return result is not None


# ---------------- XP SYSTEM ---------------- #

def add_exp_to_user(user_id, exp_gain):
    conn = get_db_connection()
    cursor = conn.cursor()

    user = cursor.execute(
        "SELECT current_xp, next_level_xp, level FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if user:
        current_xp = user["current_xp"]
        next_level_xp = user["next_level_xp"]
        current_level = user["level"]

        new_xp = current_xp + exp_gain

        while new_xp >= next_level_xp:
            new_xp -= next_level_xp
            current_level += 1
            next_level_xp += 50

        cursor.execute(
            "UPDATE users SET current_xp=?, next_level_xp=?, level=? WHERE id=?",
            (new_xp, next_level_xp, current_level, user_id)
        )
        conn.commit()

    conn.close()


def get_user_level_info(user_id):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT current_xp, level FROM users WHERE id=?",
        (user_id,)
    ).fetchone()
    conn.close()

    if user:
        return {"exp": user["current_xp"], "level": user["level"]}
    return {"exp": 0, "level": 1}


def update_user_avatar(user_id, avatar_filename):
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET avatar=? WHERE id=?",
        (avatar_filename, user_id)
    )
    conn.commit()
    conn.close()

def save_status_db(user_id, anime_id, status):
    conn = get_db_connection()

    existing = conn.execute(
        "SELECT id FROM user_anime_status WHERE user_id=? AND anime_id=?",
        (user_id, anime_id)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE user_anime_status SET status=? WHERE user_id=? AND anime_id=?",
            (status, user_id, anime_id)
        )
    else:
        conn.execute(
            "INSERT INTO user_anime_status (user_id, anime_id, status) VALUES (?, ?, ?)",
            (user_id, anime_id, status)
        )

    conn.commit()
    conn.close()

def get_status_db(user_id, anime_id):
    conn = get_db_connection()
    result = conn.execute(
        "SELECT status FROM user_anime_status WHERE user_id=? AND anime_id=?",
        (user_id, anime_id)
    ).fetchone()
    conn.close()
    return result["status"] if result else None

def get_user_favorites_with_status(user_id):
    conn = get_db_connection()
    results = conn.execute("""
        SELECT f.*, s.status
        FROM favorites f
        LEFT JOIN user_anime_status s
        ON f.user_id = s.user_id AND f.anime_id = s.anime_id
        WHERE f.user_id = ?
    """, (user_id,)).fetchall()
    conn.close()
    return results
