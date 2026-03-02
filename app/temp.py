import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "database.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_columns(conn, table_name):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_user_profile_columns(conn):
    cols = get_columns(conn, "users")
    if "bio" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
    if "banner_url" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN banner_url TEXT DEFAULT ''")
    if "theme_color" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN theme_color TEXT DEFAULT '#40e0d0'")


def ensure_media_columns(conn):
    fav_cols = get_columns(conn, "favorites")
    if "media_type" not in fav_cols:
        conn.execute("ALTER TABLE favorites ADD COLUMN media_type TEXT DEFAULT 'anime'")
    conn.execute("UPDATE favorites SET media_type = 'anime' WHERE media_type IS NULL OR media_type = ''")

    status_cols = get_columns(conn, "user_anime_status")
    if "media_type" not in status_cols:
        conn.execute("ALTER TABLE user_anime_status ADD COLUMN media_type TEXT DEFAULT 'anime'")
    conn.execute(
        "UPDATE user_anime_status SET media_type = 'anime' WHERE media_type IS NULL OR media_type = ''"
    )


def create_tables():
    conn = get_conn()

    conn.execute(
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

    ensure_user_profile_columns(conn)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            anime_id INTEGER NOT NULL,
            anime_title TEXT NOT NULL,
            anime_image TEXT NOT NULL,
            media_type TEXT DEFAULT 'anime',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    conn.execute(
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

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_anime_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            anime_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            media_type TEXT DEFAULT 'anime',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    ensure_media_columns(conn)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_tables()
    print(f"Database initialized: {DB_PATH}")
