import sqlite3

DATABASE_PATH = "database.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _get_existing_columns(connection, table_name):
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_user_profile_columns(connection):
    existing_columns = _get_existing_columns(connection, "users")

    if "bio" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
    if "banner_url" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN banner_url TEXT DEFAULT ''")
    if "theme_color" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN theme_color TEXT DEFAULT '#40e0d0'")


def _ensure_media_columns(connection):
    favorites_columns = _get_existing_columns(connection, "favorites")
    if "media_type" not in favorites_columns:
        connection.execute("ALTER TABLE favorites ADD COLUMN media_type TEXT DEFAULT 'anime'")
    connection.execute("UPDATE favorites SET media_type = 'anime' WHERE media_type IS NULL OR media_type = ''")

    status_columns = _get_existing_columns(connection, "user_anime_status")
    if "media_type" not in status_columns:
        connection.execute("ALTER TABLE user_anime_status ADD COLUMN media_type TEXT DEFAULT 'anime'")
    connection.execute(
        "UPDATE user_anime_status SET media_type = 'anime' WHERE media_type IS NULL OR media_type = ''"
    )


def _ensure_quiz_columns(connection):
    quiz_attempt_columns = _get_existing_columns(connection, "quiz_attempts")
    if "media_type" not in quiz_attempt_columns:
        connection.execute("ALTER TABLE quiz_attempts ADD COLUMN media_type TEXT DEFAULT 'anime'")
    connection.execute("UPDATE quiz_attempts SET media_type = 'anime' WHERE media_type IS NULL OR media_type = ''")


def _ensure_comment_columns(connection):
    comment_columns = _get_existing_columns(connection, "comments")
    if "media_type" not in comment_columns:
        connection.execute("ALTER TABLE comments ADD COLUMN media_type TEXT DEFAULT 'anime'")
    connection.execute("UPDATE comments SET media_type = 'anime' WHERE media_type IS NULL OR media_type = ''")


def _question_exists(connection, media_type, question_text):
    row = connection.execute(
        "SELECT 1 FROM quiz_questions WHERE media_type = ? AND question_text = ? LIMIT 1",
        (media_type, question_text),
    ).fetchone()
    return row is not None


def _insert_quiz_question(connection, question):
    if _question_exists(connection, question["media_type"], question["question_text"]):
        return False

    cursor = connection.execute(
        """
        INSERT INTO quiz_questions (media_type, difficulty, question_text, explanation, is_active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (
            question["media_type"],
            question["difficulty"],
            question["question_text"],
            question.get("explanation", ""),
        ),
    )
    question_id = cursor.lastrowid

    for option_text in question["options"]:
        connection.execute(
            """
            INSERT INTO quiz_options (question_id, option_text, is_correct)
            VALUES (?, ?, ?)
            """,
            (question_id, option_text, 1 if option_text == question["correct"] else 0),
        )
    return True


def _pick_three_distinct(items, start_index):
    picked = []
    idx = start_index
    while len(picked) < 3:
        picked.append(items[idx % len(items)])
        idx += 1
    return picked


def _build_anime_seed_bank():
    anime_pairs = [
        ("Naruto", "Naruto Uzumaki"),
        ("One Piece", "Monkey D. Luffy"),
        ("Bleach", "Ichigo Kurosaki"),
        ("Dragon Ball Z", "Goku"),
        ("Attack on Titan", "Eren Yeager"),
        ("My Hero Academia", "Izuku Midoriya"),
        ("Demon Slayer", "Tanjiro Kamado"),
        ("Jujutsu Kaisen", "Yuji Itadori"),
        ("Death Note", "Light Yagami"),
        ("Fullmetal Alchemist: Brotherhood", "Edward Elric"),
        ("Hunter x Hunter", "Gon Freecss"),
        ("Black Clover", "Asta"),
        ("Tokyo Ghoul", "Ken Kaneki"),
        ("Sword Art Online", "Kirito"),
        ("Re:Zero", "Subaru Natsuki"),
        ("Steins;Gate", "Rintaro Okabe"),
        ("Code Geass", "Lelouch Lamperouge"),
        ("Cowboy Bebop", "Spike Spiegel"),
        ("Trigun", "Vash the Stampede"),
        ("Mob Psycho 100", "Shigeo Kageyama"),
        ("One Punch Man", "Saitama"),
        ("Fairy Tail", "Natsu Dragneel"),
        ("JoJo's Bizarre Adventure: Phantom Blood", "Jonathan Joestar"),
        ("Haikyuu!!", "Shoyo Hinata"),
        ("Kuroko's Basketball", "Tetsuya Kuroko"),
        ("Blue Lock", "Yoichi Isagi"),
        ("Dr. Stone", "Senku Ishigami"),
        ("The Rising of the Shield Hero", "Naofumi Iwatani"),
        ("That Time I Got Reincarnated as a Slime", "Rimuru Tempest"),
        ("Noragami", "Yato"),
        ("Chainsaw Man", "Denji"),
        ("Spy x Family", "Loid Forger"),
        ("Tokyo Revengers", "Takemichi Hanagaki"),
        ("Vinland Saga", "Thorfinn"),
    ]

    all_titles = [title for title, _ in anime_pairs]
    all_heroes = [hero for _, hero in anime_pairs]
    bank = []

    for idx, (title, hero) in enumerate(anime_pairs):
        wrong_heroes = [name for name in all_heroes if name != hero]
        wrong_titles = [name for name in all_titles if name != title]

        hero_options = [hero] + _pick_three_distinct(wrong_heroes, idx)
        title_options = [title] + _pick_three_distinct(wrong_titles, idx)
        belongs_options = [hero] + _pick_three_distinct(wrong_heroes, idx + 7)

        bank.append(
            {
                "media_type": "anime",
                "difficulty": "easy",
                "question_text": f"Who is the main protagonist of {title}?",
                "options": hero_options,
                "correct": hero,
                "explanation": f"{hero} is the central lead character in {title}.",
            }
        )
        bank.append(
            {
                "media_type": "anime",
                "difficulty": "medium",
                "question_text": f"In which anime is {hero} the main protagonist?",
                "options": title_options,
                "correct": title,
                "explanation": f"{hero} is the main protagonist of {title}.",
            }
        )
        bank.append(
            {
                "media_type": "anime",
                "difficulty": "hard",
                "question_text": f"Which character belongs to the anime {title}?",
                "options": belongs_options,
                "correct": hero,
                "explanation": f"{hero} is a key character from {title}.",
            }
        )

    return bank[:100]


def _seed_quiz_data(connection):
    anime_count_row = connection.execute(
        "SELECT COUNT(*) AS total FROM quiz_questions WHERE media_type = 'anime'"
    ).fetchone()
    anime_count = anime_count_row["total"] if anime_count_row else 0

    if anime_count < 100:
        for question in _build_anime_seed_bank():
            if anime_count >= 100:
                break
            if _insert_quiz_question(connection, question):
                anime_count += 1

    extra_bank = [
        {
            "media_type": "manga",
            "difficulty": "easy",
            "question_text": "Which manga is centered around a notebook that kills people?",
            "options": ["Naruto", "Death Note", "Haikyuu!!", "Black Clover"],
            "correct": "Death Note",
            "explanation": "Death Note revolves around the supernatural notebook called Death Note.",
        },
        {
            "media_type": "manga",
            "difficulty": "medium",
            "question_text": "Who wrote One Piece?",
            "options": ["Masashi Kishimoto", "Eiichiro Oda", "Tite Kubo", "Yoshihiro Togashi"],
            "correct": "Eiichiro Oda",
            "explanation": "Eiichiro Oda is the author of One Piece.",
        },
        {
            "media_type": "lightnovel",
            "difficulty": "easy",
            "question_text": "Re:Zero started as what format before major adaptation?",
            "options": ["Web novel", "Movie script", "Game manual", "Manga one-shot"],
            "correct": "Web novel",
            "explanation": "Re:Zero began as a web novel by Tappei Nagatsuki.",
        },
        {
            "media_type": "lightnovel",
            "difficulty": "medium",
            "question_text": "Which title is a popular light novel series by Kugane Maruyama?",
            "options": ["Overlord", "Bakemonogatari", "No Game No Life", "Classroom of the Elite"],
            "correct": "Overlord",
            "explanation": "Overlord is written by Kugane Maruyama.",
        },
    ]

    for question in extra_bank:
        _insert_quiz_question(connection, question)


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
            media_type TEXT DEFAULT 'anime',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            anime_id INTEGER NOT NULL,
            media_type TEXT DEFAULT 'anime',
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
            media_type TEXT DEFAULT 'anime',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_type TEXT NOT NULL DEFAULT 'anime',
            difficulty TEXT NOT NULL DEFAULT 'easy',
            question_text TEXT NOT NULL,
            explanation TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1
        );
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            option_text TEXT NOT NULL,
            is_correct INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (question_id) REFERENCES quiz_questions(id)
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
            media_type TEXT DEFAULT 'anime',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    _ensure_media_columns(connection)
    _ensure_quiz_columns(connection)
    _ensure_comment_columns(connection)
    _seed_quiz_data(connection)

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


def add_favorite_db(user_id, anime_id, title, image, media_type="anime"):
    connection = get_db_connection()
    connection.execute(
        """
        INSERT INTO favorites (user_id, anime_id, anime_title, anime_image, media_type)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, anime_id, title, image, media_type),
    )
    connection.commit()
    connection.close()


def remove_favorite_db(user_id, anime_id, media_type="anime"):
    connection = get_db_connection()
    connection.execute(
        "DELETE FROM favorites WHERE user_id = ? AND anime_id = ? AND media_type = ?",
        (user_id, anime_id, media_type),
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


def check_favorite(user_id, anime_id, media_type="anime"):
    connection = get_db_connection()
    match = connection.execute(
        "SELECT 1 FROM favorites WHERE user_id = ? AND anime_id = ? AND media_type = ?",
        (user_id, anime_id, media_type),
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


def save_status_db(user_id, anime_id, status, media_type="anime"):
    connection = get_db_connection()

    existing = connection.execute(
        """
        SELECT id FROM user_anime_status
        WHERE user_id = ? AND anime_id = ? AND media_type = ?
        """,
        (user_id, anime_id, media_type),
    ).fetchone()

    if existing:
        connection.execute(
            """
            UPDATE user_anime_status
            SET status = ?
            WHERE user_id = ? AND anime_id = ? AND media_type = ?
            """,
            (status, user_id, anime_id, media_type),
        )
    else:
        connection.execute(
            """
            INSERT INTO user_anime_status (user_id, anime_id, status, media_type)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, anime_id, status, media_type),
        )

    connection.commit()
    connection.close()


def get_status_db(user_id, anime_id, media_type="anime"):
    connection = get_db_connection()
    row = connection.execute(
        """
        SELECT status FROM user_anime_status
        WHERE user_id = ? AND anime_id = ? AND media_type = ?
        """,
        (user_id, anime_id, media_type),
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
          ON f.user_id = s.user_id
         AND f.anime_id = s.anime_id
         AND f.media_type = s.media_type
        WHERE f.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    connection.close()
    return rows


def add_comment_db(user_id, anime_id, content, media_type="anime"):
    connection = get_db_connection()
    connection.execute(
        """
        INSERT INTO comments (user_id, anime_id, media_type, content)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, anime_id, media_type, content),
    )
    connection.commit()
    connection.close()


def get_comments_for_anime(anime_id, media_type="anime"):
    connection = get_db_connection()
    rows = connection.execute(
        """
        SELECT c.id, c.user_id, c.anime_id, c.media_type, c.content, c.created_at, u.username
        FROM comments AS c
        JOIN users AS u ON u.id = c.user_id
        WHERE c.anime_id = ? AND c.media_type = ?
        ORDER BY c.created_at DESC
        """,
        (anime_id, media_type),
    ).fetchall()
    connection.close()
    return rows
