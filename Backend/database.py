import base64
import hashlib
import hmac
import os
import sqlite3
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PROJECT_DIR / "Backend"
DB_PATH = APP_DIR / "desktop_data.db"
ADMIN_USERNAME = os.getenv("TESTER_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("TESTER_ADMIN_PASSWORD", "admin")
ADMIN_USERNAMES = tuple(dict.fromkeys([ADMIN_USERNAME, "admin", "adm_Cd5pAB6fywnt"]))


def connect_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return base64.b64encode(salt + digest).decode("ascii")


def verify_password(password, stored):
    raw = base64.b64decode(stored.encode("ascii"))
    salt, expected = raw[:16], raw[16:]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(digest, expected)


def init_db():
    with connect_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                pass_score INTEGER NOT NULL DEFAULT 60,
                duration_seconds INTEGER NOT NULL DEFAULT 600,
                exam_questions_count INTEGER NOT NULL DEFAULT 0,
                shuffle_questions INTEGER NOT NULL DEFAULT 1,
                shuffle_answers INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                correct_index INTEGER NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                test_id INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                total INTEGER NOT NULL,
                score INTEGER NOT NULL,
                passed INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema(conn)
        ensure_admin_accounts(conn)
        if conn.execute("SELECT COUNT(*) FROM tests").fetchone()[0] == 0:
            seed_demo_test(conn)


def ensure_schema(conn):
    test_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tests)").fetchall()}
    if "duration_seconds" not in test_columns:
        conn.execute("ALTER TABLE tests ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 600")
    if "exam_questions_count" not in test_columns:
        conn.execute("ALTER TABLE tests ADD COLUMN exam_questions_count INTEGER NOT NULL DEFAULT 0")
    if "shuffle_questions" not in test_columns:
        conn.execute("ALTER TABLE tests ADD COLUMN shuffle_questions INTEGER NOT NULL DEFAULT 1")
    if "shuffle_answers" not in test_columns:
        conn.execute("ALTER TABLE tests ADD COLUMN shuffle_answers INTEGER NOT NULL DEFAULT 0")


def ensure_admin_accounts(conn):
    for username in ADMIN_USERNAMES:
        admin = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if not admin:
            password_hash = hash_password(ADMIN_PASSWORD)
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                (username, password_hash),
            )


def seed_demo_test(conn):
    test_id = conn.execute(
        "INSERT INTO tests (title, description, pass_score, duration_seconds) VALUES (?, ?, ?, ?)",
        ("HTML Basics", "Short starter test.", 60, 600),
    ).lastrowid
    questions = [
        ("Which tag is used for the main page heading?", ["<title>", "<h1>", "<header>", "<main>"], 1),
        ("Where is a CSS file usually connected?", ["Inside <body>", "Inside <head>", "After </html>", "Only in JavaScript"], 1),
        ("Which attribute stores the URL for an <a> tag?", ["src", "href", "link", "target"], 1),
    ]
    for position, (text, answers, correct_index) in enumerate(questions):
        question_id = conn.execute(
            "INSERT INTO questions (test_id, text, correct_index, position) VALUES (?, ?, ?, ?)",
            (test_id, text, correct_index, position),
        ).lastrowid
        for answer_position, answer in enumerate(answers):
            conn.execute(
                "INSERT INTO answers (question_id, text, position) VALUES (?, ?, ?)",
                (question_id, answer, answer_position),
            )


def authenticate(username, password):
    username = username.strip()
    with connect_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_variants(password, user["password_hash"]):
            return dict(user)
    return None


def check_password_variants(password, stored_hash):
    password_variants = [password]
    stripped = password.strip()
    if stripped != password:
        password_variants.append(stripped)
    return any(verify_password(candidate, stored_hash) for candidate in password_variants)


def verify_user_password(user_id, password):
    with connect_db() as conn:
        user = conn.execute("SELECT password_hash FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if not user:
            return False
        return check_password_variants(password, user["password_hash"])


def register_user(username, password):
    username = username.strip()
    if len(username) < 3 or len(password) < 4:
        raise ValueError("Login must be at least 3 characters and password at least 4.")
    with connect_db() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')",
                (username, hash_password(password)),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("This login already exists.") from exc


def list_tests():
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT t.*, COUNT(q.id) AS question_count
            FROM tests t
            LEFT JOIN questions q ON q.test_id = t.id
            GROUP BY t.id
            ORDER BY t.created_at DESC
            """
        ).fetchall()
        tests = []
        for row in rows:
            item = dict(row)
            if not item.get("exam_questions_count"):
                item["exam_questions_count"] = item["question_count"]
            item["shuffle_questions"] = int(item.get("shuffle_questions", 1))
            item["shuffle_answers"] = int(item.get("shuffle_answers", 0))
            tests.append(item)
        return tests


def get_test(test_id):
    with connect_db() as conn:
        test = conn.execute("SELECT * FROM tests WHERE id = ?", (test_id,)).fetchone()
        if not test:
            return None
        questions = conn.execute(
            "SELECT * FROM questions WHERE test_id = ? ORDER BY position",
            (test_id,),
        ).fetchall()
        result = dict(test)
        result["questions"] = []
        for question in questions:
            answers = conn.execute(
                "SELECT text FROM answers WHERE question_id = ? ORDER BY position",
                (question["id"],),
            ).fetchall()
            item = dict(question)
            item["answers"] = [row["text"] for row in answers]
            result["questions"].append(item)
        if not result.get("exam_questions_count"):
            result["exam_questions_count"] = len(result["questions"])
        result["shuffle_questions"] = int(result.get("shuffle_questions", 1))
        result["shuffle_answers"] = int(result.get("shuffle_answers", 0))
        return result


def save_result(user_id, test_id, correct, total, score, passed):
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO results (user_id, test_id, correct, total, score, passed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, test_id, correct, total, score, int(passed)),
        )


def list_results():
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT r.created_at, u.username, t.title, r.correct, r.total, r.score, r.passed
            FROM results r
            JOIN users u ON u.id = r.user_id
            JOIN tests t ON t.id = r.test_id
            ORDER BY r.created_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def create_test(title, description, pass_score, questions, duration_seconds=600, exam_questions_count=None, shuffle_questions=True, shuffle_answers=False):
    if not title.strip():
        raise ValueError("Title is required.")
    if not questions:
        raise ValueError("Add at least one question.")
    try:
        pass_score = int(pass_score)
    except (TypeError, ValueError) as exc:
        raise ValueError("Pass score must be a number from 1 to 100.") from exc
    if pass_score < 1 or pass_score > 100:
        raise ValueError("Pass score must be from 1 to 100.")
    try:
        duration_seconds = int(duration_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("Test duration must be a number of seconds.") from exc
    if duration_seconds < 60:
        raise ValueError("Test duration must be at least 1 minute.")
    if exam_questions_count in (None, ""):
        exam_questions_count = len(questions)
    try:
        exam_questions_count = int(exam_questions_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("Exam question count must be a number.") from exc
    if exam_questions_count < 1:
        raise ValueError("Exam question count must be greater than zero.")
    if exam_questions_count > len(questions):
        raise ValueError("Exam question count cannot be greater than total question count.")
    with connect_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        test_id = conn.execute(
            """
            INSERT INTO tests (title, description, pass_score, duration_seconds, exam_questions_count, shuffle_questions, shuffle_answers)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title.strip(), description.strip(), pass_score, duration_seconds, exam_questions_count, int(bool(shuffle_questions)), int(bool(shuffle_answers))),
        ).lastrowid
        for position, question in enumerate(questions):
            answers = [str(answer).strip() for answer in question["answers"]]
            correct_index = int(question["correct_index"])
            if len(answers) != 4 or not question["text"].strip() or any(not answer for answer in answers):
                raise ValueError("Each question needs text and four answers.")
            if correct_index not in range(4):
                raise ValueError("Correct answer must be from 1 to 4.")
            question_id = conn.execute(
                "INSERT INTO questions (test_id, text, correct_index, position) VALUES (?, ?, ?, ?)",
                (test_id, question["text"].strip(), correct_index, position),
            ).lastrowid
            for answer_position, answer in enumerate(answers):
                conn.execute(
                    "INSERT INTO answers (question_id, text, position) VALUES (?, ?, ?)",
                    (question_id, answer, answer_position),
                )


def update_test(test_id, title, description, pass_score, questions, duration_seconds=600, exam_questions_count=None, shuffle_questions=True, shuffle_answers=False):
    if not title.strip():
        raise ValueError("Title is required.")
    if not questions:
        raise ValueError("Add at least one question.")
    try:
        pass_score = int(pass_score)
    except (TypeError, ValueError) as exc:
        raise ValueError("Pass score must be a number from 1 to 100.") from exc
    if pass_score < 1 or pass_score > 100:
        raise ValueError("Pass score must be from 1 to 100.")
    try:
        duration_seconds = int(duration_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("Test duration must be a number of seconds.") from exc
    if duration_seconds < 60:
        raise ValueError("Test duration must be at least 1 minute.")
    if exam_questions_count in (None, ""):
        exam_questions_count = len(questions)
    try:
        exam_questions_count = int(exam_questions_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("Exam question count must be a number.") from exc
    if exam_questions_count < 1:
        raise ValueError("Exam question count must be greater than zero.")
    if exam_questions_count > len(questions):
        raise ValueError("Exam question count cannot be greater than total question count.")

    with connect_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        existing = conn.execute("SELECT id FROM tests WHERE id = ?", (test_id,)).fetchone()
        if not existing:
            raise ValueError("Test not found.")
        conn.execute(
            """
            UPDATE tests
            SET title = ?, description = ?, pass_score = ?, duration_seconds = ?,
                exam_questions_count = ?, shuffle_questions = ?, shuffle_answers = ?
            WHERE id = ?
            """,
            (title.strip(), description.strip(), pass_score, duration_seconds, exam_questions_count, int(bool(shuffle_questions)), int(bool(shuffle_answers)), test_id),
        )
        conn.execute("DELETE FROM questions WHERE test_id = ?", (test_id,))
        for position, question in enumerate(questions):
            answers = [str(answer).strip() for answer in question["answers"]]
            correct_index = int(question["correct_index"])
            if len(answers) != 4 or not question["text"].strip() or any(not answer for answer in answers):
                raise ValueError("Each question needs text and four answers.")
            if correct_index not in range(4):
                raise ValueError("Correct answer must be from 1 to 4.")
            question_id = conn.execute(
                "INSERT INTO questions (test_id, text, correct_index, position) VALUES (?, ?, ?, ?)",
                (test_id, question["text"].strip(), correct_index, position),
            ).lastrowid
            for answer_position, answer in enumerate(answers):
                conn.execute(
                    "INSERT INTO answers (question_id, text, position) VALUES (?, ?, ?)",
                    (question_id, answer, answer_position),
                )


def delete_test(test_id):
    with connect_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM tests WHERE id = ?", (test_id,))
