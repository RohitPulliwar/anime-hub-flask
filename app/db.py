import sqlite3

DATABASE_PATH = "database.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_user_profile_columns(connection):
    existing_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }

    if "bio" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
    if "banner_url" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN banner_url TEXT DEFAULT ''")
    if "theme_color" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN theme_color TEXT DEFAULT '#40e0d0'")


def init_db():
    connection = get_db_connection()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            current_xp INTEGER DEFAULT 0,
            next_level_xp INTEGER DEFAULT 100,
            level INTEGER DEFAULT 1,
            avatar TEXT DEFAULT 'default.png'
        );
        """
    )

    _ensure_user_profile_columns(connection)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            anime_id INTEGER NOT NULL,
            anime_title TEXT NOT NULL,
            anime_image TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            score INTEGER DEFAULT 0,
            exp_earned INTEGER DEFAULT 0,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS user_anime_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            anime_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    connection.commit()
    connection.close()


def create_user(username, password_hash):
    connection = get_db_connection()
    connection.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (username, password_hash),
    )
    connection.commit()
    connection.close()


def get_user_by_username(username):
    connection = get_db_connection()
    user = connection.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    connection.close()
    return user


def get_user_by_id(user_id):
    connection = get_db_connection()
    user = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    connection.close()
    return user


def add_favorite_db(user_id, anime_id, title, image):
    connection = get_db_connection()
    connection.execute(
        """
        INSERT INTO favorites (user_id, anime_id, anime_title, anime_image)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, anime_id, title, image),
    )
    connection.commit()
    connection.close()


def remove_favorite_db(user_id, anime_id):
    connection = get_db_connection()
    connection.execute(
        "DELETE FROM favorites WHERE user_id = ? AND anime_id = ?",
        (user_id, anime_id),
    )
    connection.commit()
    connection.close()


def get_user_favorites(user_id):
    connection = get_db_connection()
    rows = connection.execute(
        "SELECT * FROM favorites WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    connection.close()
    return rows


def check_favorite(user_id, anime_id):
    connection = get_db_connection()
    match = connection.execute(
        "SELECT 1 FROM favorites WHERE user_id = ? AND anime_id = ?",
        (user_id, anime_id),
    ).fetchone()
    connection.close()
    return match is not None


def add_exp_to_user(user_id, exp_gain):
    connection = get_db_connection()
    cursor = connection.cursor()

    user = cursor.execute(
        "SELECT current_xp, next_level_xp, level FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if not user:
        connection.close()
        return

    current_xp = user["current_xp"]
    next_level_xp = user["next_level_xp"]
    level = user["level"]
    accumulated_xp = current_xp + exp_gain

    while accumulated_xp >= next_level_xp:
        accumulated_xp -= next_level_xp
        level += 1
        next_level_xp += 50

    cursor.execute(
        """
        UPDATE users
        SET current_xp = ?, next_level_xp = ?, level = ?
        WHERE id = ?
        """,
        (accumulated_xp, next_level_xp, level, user_id),
    )

    connection.commit()
    connection.close()


def get_user_level_info(user_id):
    connection = get_db_connection()
    user = connection.execute(
        "SELECT current_xp, level FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    connection.close()

    if not user:
        return {"exp": 0, "level": 1}

    return {"exp": user["current_xp"], "level": user["level"]}


def update_user_avatar(user_id, avatar_filename):
    connection = get_db_connection()
    connection.execute(
        "UPDATE users SET avatar = ? WHERE id = ?",
        (avatar_filename, user_id),
    )
    connection.commit()
    connection.close()


def save_status_db(user_id, anime_id, status):
    connection = get_db_connection()

    existing = connection.execute(
        "SELECT id FROM user_anime_status WHERE user_id = ? AND anime_id = ?",
        (user_id, anime_id),
    ).fetchone()

    if existing:
        connection.execute(
            """
            UPDATE user_anime_status
            SET status = ?
            WHERE user_id = ? AND anime_id = ?
            """,
            (status, user_id, anime_id),
        )
    else:
        connection.execute(
            """
            INSERT INTO user_anime_status (user_id, anime_id, status)
            VALUES (?, ?, ?)
            """,
            (user_id, anime_id, status),
        )

    connection.commit()
    connection.close()


def get_status_db(user_id, anime_id):
    connection = get_db_connection()
    row = connection.execute(
        "SELECT status FROM user_anime_status WHERE user_id = ? AND anime_id = ?",
        (user_id, anime_id),
    ).fetchone()
    connection.close()

    return row["status"] if row else None


def get_user_favorites_with_status(user_id):
    connection = get_db_connection()
    rows = connection.execute(
        """
        SELECT f.*, s.status
        FROM favorites AS f
        LEFT JOIN user_anime_status AS s
          ON f.user_id = s.user_id AND f.anime_id = s.anime_id
        WHERE f.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    connection.close()
    return rows
