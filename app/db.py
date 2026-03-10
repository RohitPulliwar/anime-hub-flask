import os
import re

from psycopg import connect
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/self_flask",
)


class DuplicateUsernameError(Exception):
    pass


def _to_pg_query(query):
    # Keep existing sqlite-style "?" placeholders working across the codebase.
    return query.replace("?", "%s")


class _CursorAdapter:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=()):
        self._cursor.execute(_to_pg_query(query), params or ())
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        return getattr(self._cursor, "lastrowid", None)

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _ConnectionAdapter:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, query, params=()):
        cursor = self._connection.execute(_to_pg_query(query), params or ())
        return _CursorAdapter(cursor)

    def cursor(self):
        return _CursorAdapter(self._connection.cursor())

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __getattr__(self, name):
        return getattr(self._connection, name)


def get_db_connection():
    connection = connect(DATABASE_URL, row_factory=dict_row)
    return _ConnectionAdapter(connection)


def _get_existing_columns(connection, table_name):
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ?
        """,
        (table_name,),
    ).fetchall()
    return {row["column_name"] for row in rows}


def _ensure_user_profile_columns(connection):
    existing_columns = _get_existing_columns(connection, "users")

    if "bio" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
    if "banner_url" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN banner_url TEXT DEFAULT ''")
    if "theme_color" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN theme_color TEXT DEFAULT '#40e0d0'")
    if "avatar_frame" not in existing_columns:
        connection.execute("ALTER TABLE users ADD COLUMN avatar_frame TEXT DEFAULT 'none'")


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

    quiz_question_columns = _get_existing_columns(connection, "quiz_questions")
    if "quiz_tag" not in quiz_question_columns:
        connection.execute("ALTER TABLE quiz_questions ADD COLUMN quiz_tag TEXT DEFAULT 'all'")
    connection.execute("UPDATE quiz_questions SET quiz_tag = 'all' WHERE quiz_tag IS NULL OR quiz_tag = ''")


def _ensure_comment_columns(connection):
    comment_columns = _get_existing_columns(connection, "comments")
    if "media_type" not in comment_columns:
        connection.execute("ALTER TABLE comments ADD COLUMN media_type TEXT DEFAULT 'anime'")
    connection.execute("UPDATE comments SET media_type = 'anime' WHERE media_type IS NULL OR media_type = ''")


def _question_exists(connection, media_type, quiz_tag, question_text):
    row = connection.execute(
        "SELECT 1 FROM quiz_questions WHERE media_type = ? AND quiz_tag = ? AND question_text = ? LIMIT 1",
        (media_type, quiz_tag, question_text),
    ).fetchone()
    return row is not None


def _insert_quiz_question(connection, question):
    quiz_tag = question.get("quiz_tag", "all")
    if _question_exists(connection, question["media_type"], quiz_tag, question["question_text"]):
        return False

    cursor = connection.execute(
        """
        INSERT INTO quiz_questions (media_type, quiz_tag, difficulty, question_text, explanation, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
        RETURNING id
        """,
        (
            question["media_type"],
            quiz_tag,
            question["difficulty"],
            question["question_text"],
            question.get("explanation", ""),
        ),
    )
    row = cursor.fetchone()
    question_id = row["id"]

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


def _quiz_tag(label):
    return re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")


def _build_media_quiz_bank(media_type, topic_bank):
    all_protagonists = [data["protagonist"] for data in topic_bank.values()]
    all_characters = [name for data in topic_bank.values() for name in data["easy_characters"]]
    all_medium_terms = [term for data in topic_bank.values() for term in data["medium_terms"]]
    all_hard_terms = [term for data in topic_bank.values() for term in data["hard_terms"]]
    quiz_bank = []

    for title, data in topic_bank.items():
        quiz_tag = _quiz_tag(title)
        protagonist = data["protagonist"]
        easy_characters = data["easy_characters"]
        medium_terms = data["medium_terms"]
        hard_terms = data["hard_terms"]

        protagonist_options = [protagonist] + _pick_three_distinct(
            [name for name in all_protagonists if name != protagonist], 0
        )
        quiz_bank.append(
            {
                "media_type": media_type,
                "quiz_tag": quiz_tag,
                "difficulty": "easy",
                "question_text": f"Who is the main protagonist of {title}?",
                "options": protagonist_options,
                "correct": protagonist,
                "explanation": f"{protagonist} is the main protagonist of {title}.",
            }
        )

        for idx, character in enumerate(easy_characters[1:], start=1):
            wrong_pool = [name for name in all_characters if name != character and name not in easy_characters]
            options = [character] + _pick_three_distinct(wrong_pool, idx)
            quiz_bank.append(
                {
                    "media_type": media_type,
                    "quiz_tag": quiz_tag,
                    "difficulty": "easy",
                    "question_text": f"Which character belongs to {title}?",
                    "options": options,
                    "correct": character,
                    "explanation": f"{character} is a character from {title}.",
                }
            )

        for idx, term in enumerate(medium_terms):
            wrong_pool = [item for item in all_medium_terms if item != term and item not in medium_terms]
            options = [term] + _pick_three_distinct(wrong_pool, idx)
            quiz_bank.append(
                {
                    "media_type": media_type,
                    "quiz_tag": quiz_tag,
                    "difficulty": "medium",
                    "question_text": f"Which term is most associated with {title}?",
                    "options": options,
                    "correct": term,
                    "explanation": f"{term} is a key term in {title}.",
                }
            )

        for idx, term in enumerate(hard_terms):
            wrong_pool = [item for item in all_hard_terms if item != term and item not in hard_terms]
            options = [term] + _pick_three_distinct(wrong_pool, idx)
            quiz_bank.append(
                {
                    "media_type": media_type,
                    "quiz_tag": quiz_tag,
                    "difficulty": "hard",
                    "question_text": f"Which advanced term belongs to {title}?",
                    "options": options,
                    "correct": term,
                    "explanation": f"{term} is associated with {title}.",
                }
            )

    return quiz_bank


def _seed_quiz_data(connection):
    anime_bank = {
        "One Piece": {
            "protagonist": "Monkey D. Luffy",
            "easy_characters": ["Monkey D. Luffy", "Roronoa Zoro", "Nami", "Sanji", "Usopp", "Tony Tony Chopper", "Nico Robin", "Franky", "Brook", "Jinbe"],
            "medium_terms": ["Straw Hat Pirates", "Grand Line", "Red Line", "One Piece", "Devil Fruit", "Marines", "Wano", "Alabasta", "Going Merry", "Thousand Sunny"],
            "hard_terms": ["Conqueror's Haki", "Armament Haki", "Observation Haki", "Road Poneglyph", "Yonko", "Shichibukai", "Worst Generation", "Logia", "Paramecia", "Zoan"],
        },
        "Dragon Ball": {
            "protagonist": "Goku",
            "easy_characters": ["Goku", "Vegeta", "Gohan", "Piccolo", "Krillin", "Trunks", "Bulma", "Frieza", "Cell", "Majin Buu"],
            "medium_terms": ["Saiyan", "Kamehameha", "Dragon Radar", "Capsule Corp", "Namek", "Super Saiyan", "Senzu Bean", "Frieza Force", "Spirit Bomb", "Hyperbolic Time Chamber"],
            "hard_terms": ["Ultra Instinct", "Kaio-ken", "Potara Earrings", "Fusion Dance", "Instant Transmission", "Beerus", "Whis", "Zeno", "Tournament of Power", "Universe 7"],
        },
        "Naruto": {
            "protagonist": "Naruto Uzumaki",
            "easy_characters": ["Naruto Uzumaki", "Sasuke Uchiha", "Sakura Haruno", "Kakashi Hatake", "Hinata Hyuga", "Shikamaru Nara", "Gaara", "Jiraiya", "Tsunade", "Rock Lee"],
            "medium_terms": ["Hidden Leaf", "Hokage", "Chunin Exams", "Akatsuki", "Rasengan", "Sharingan", "Shadow Clone Jutsu", "Tailed Beast", "Sage Mode", "Konoha"],
            "hard_terms": ["Mangekyo Sharingan", "Rinnegan", "Susanoo", "Amaterasu", "Tsukuyomi", "Edo Tensei", "Six Paths Sage Mode", "Eight Gates", "Kotoamatsukami", "Chidori"],
        },
        "Bleach": {
            "protagonist": "Ichigo Kurosaki",
            "easy_characters": ["Ichigo Kurosaki", "Rukia Kuchiki", "Orihime Inoue", "Uryu Ishida", "Yasutora Sado", "Renji Abarai", "Byakuya Kuchiki", "Toshiro Hitsugaya", "Kenpachi Zaraki", "Sosuke Aizen"],
            "medium_terms": ["Soul Reaper", "Soul Society", "Zanpakuto", "Bankai", "Hollow", "Gotei 13", "Hueco Mundo", "Arrancar", "Quincy", "Seireitei"],
            "hard_terms": ["Getsuga Tensho", "Mugetsu", "Senbonzakura Kageyoshi", "Daiguren Hyorinmaru", "Hogyoku", "Fullbring", "Vasto Lorde", "The Almighty", "Schrift", "Dangai"],
        },
    }

    manga_bank = {
        "One Piece": {
            "protagonist": "Monkey D. Luffy",
            "easy_characters": ["Monkey D. Luffy", "Roronoa Zoro", "Nami", "Sanji", "Usopp", "Tony Tony Chopper", "Nico Robin", "Franky", "Brook", "Jinbe"],
            "medium_terms": ["Eiichiro Oda", "Weekly Shonen Jump", "Grand Line", "Wano", "Alabasta", "Dressrosa", "Marineford", "Poneglyph", "Devil Fruit", "Straw Hat Pirates"],
            "hard_terms": ["Void Century", "Road Poneglyph", "Impel Down", "Enies Lobby", "Gear Fifth", "Haki", "Yonko", "Reverie", "Laugh Tale", "Ancient Weapons"],
        },
        "Dragon Ball": {
            "protagonist": "Goku",
            "easy_characters": ["Goku", "Vegeta", "Gohan", "Piccolo", "Krillin", "Trunks", "Bulma", "Frieza", "Cell", "Majin Buu"],
            "medium_terms": ["Akira Toriyama", "Weekly Shonen Jump", "Saiyan Saga", "Namek Saga", "Cell Saga", "Majin Buu Saga", "Kamehameha", "Capsule Corp", "Dragon Balls", "Super Saiyan"],
            "hard_terms": ["Kaio-ken", "Instant Transmission", "Spirit Bomb", "Potara Fusion", "Fusion Dance", "Z Fighters", "King Kai", "Hyperbolic Time Chamber", "Planet Namek", "World Martial Arts Tournament"],
        },
        "Naruto": {
            "protagonist": "Naruto Uzumaki",
            "easy_characters": ["Naruto Uzumaki", "Sasuke Uchiha", "Sakura Haruno", "Kakashi Hatake", "Hinata Hyuga", "Shikamaru Nara", "Gaara", "Jiraiya", "Tsunade", "Rock Lee"],
            "medium_terms": ["Masashi Kishimoto", "Weekly Shonen Jump", "Konoha", "Chunin Exams", "Akatsuki", "Rasengan", "Sharingan", "Sage Mode", "Tailed Beasts", "Hokage"],
            "hard_terms": ["Mangekyo Sharingan", "Rinnegan", "Edo Tensei", "Six Paths", "Susanoo", "Amaterasu", "Tsukuyomi", "Kekkei Genkai", "Uchiha Clan", "Will of Fire"],
        },
        "Bleach": {
            "protagonist": "Ichigo Kurosaki",
            "easy_characters": ["Ichigo Kurosaki", "Rukia Kuchiki", "Orihime Inoue", "Uryu Ishida", "Yasutora Sado", "Renji Abarai", "Byakuya Kuchiki", "Toshiro Hitsugaya", "Kenpachi Zaraki", "Sosuke Aizen"],
            "medium_terms": ["Tite Kubo", "Weekly Shonen Jump", "Soul Society", "Hueco Mundo", "Gotei 13", "Zanpakuto", "Bankai", "Arrancar", "Quincy", "Seireitei"],
            "hard_terms": ["Hogyoku", "Mugetsu", "Vasto Lorde", "Fullbring", "Schrift", "Wandenreich", "Thousand-Year Blood War", "Getsuga Tensho", "Senbonzakura", "Daiguren Hyorinmaru"],
        },
    }

    quiz_bank = _build_media_quiz_bank("anime", anime_bank)
    quiz_bank.extend(_build_media_quiz_bank("manga", manga_bank))
    inserted_count = 0
    for question in quiz_bank:
        if _insert_quiz_question(connection, question):
            inserted_count += 1

    return inserted_count


def init_db():
    connection = get_db_connection()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            current_xp INTEGER DEFAULT 0,
            next_level_xp INTEGER DEFAULT 100,
            level INTEGER DEFAULT 1,
            avatar TEXT DEFAULT 'default.png',
            avatar_frame TEXT DEFAULT 'none'
        );
        """
    )

    _ensure_user_profile_columns(connection)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            media_type TEXT NOT NULL DEFAULT 'anime',
            quiz_tag TEXT NOT NULL DEFAULT 'all',
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
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
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
    try:
        connection.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, password_hash),
        )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        if getattr(exc, "sqlstate", None) == "23505":
            raise DuplicateUsernameError from exc
        raise
    finally:
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
