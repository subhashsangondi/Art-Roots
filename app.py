import json
import os
import re
import secrets
import sqlite3
import uuid
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

from ai_service import GeminiService, GeminiServiceError


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

ALLOWED_IMAGE_FORMATS = {
    "GIF": ".gif",
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}
ROLES = {"artist", "viewer"}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.]{3,30}$")
MIN_PASSWORD_LENGTH = 6

# Every artwork query goes through this so like counts stay consistent.
# The single parameter is the current user's id (or -1 when logged out).
ARTWORK_SELECT = """
    SELECT a.*,
        (SELECT COUNT(*) FROM likes l WHERE l.artwork_id = a.id) AS likes,
        EXISTS(
            SELECT 1 FROM likes l WHERE l.artwork_id = a.id AND l.user_id = ?
        ) AS liked
    FROM artworks a
"""


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=str(BASE_DIR / "art_roots.db"),
        UPLOAD_FOLDER=str(BASE_DIR / "uploads"),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        GEMINI_API_KEY=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        GEMINI_BASE_URL=os.getenv("GEMINI_BASE_URL")
        or os.getenv("NEXUS_BASE_URL"),
        GEMINI_MODEL=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        GEMINI_FALLBACK_MODELS=os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash"),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    app.extensions["ai_service"] = GeminiService(
        api_key=app.config.get("GEMINI_API_KEY"),
        base_url=app.config.get("GEMINI_BASE_URL"),
        model=app.config["GEMINI_MODEL"],
        fallback_models=[
            name.strip() for name in app.config["GEMINI_FALLBACK_MODELS"].split(",")
        ],
    )

    app.teardown_appcontext(close_database)
    register_routes(app)
    register_error_handlers(app)

    with app.app_context():
        init_database()

    return app


def get_database():
    if "database" not in g:
        g.database = sqlite3.connect(current_app.config["DATABASE"])
        g.database.row_factory = sqlite3.Row
        g.database.execute("PRAGMA foreign_keys = ON")
    return g.database


def close_database(_error=None):
    database = g.pop("database", None)
    if database is not None:
        database.close()


def init_database():
    database = get_database()
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS artworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            description TEXT NOT NULL,
            image_url TEXT NOT NULL,
            story TEXT NOT NULL,
            tags TEXT NOT NULL,
            alt_text TEXT NOT NULL
        )
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('artist', 'viewer'))
        )
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            artwork_id INTEGER NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, artwork_id)
        )
        """
    )
    # Add columns introduced after the first release to existing databases.
    columns = {row["name"] for row in database.execute("PRAGMA table_info(artworks)")}
    if "views" not in columns:
        database.execute("ALTER TABLE artworks ADD COLUMN views INTEGER NOT NULL DEFAULT 0")
    if "created_at" not in columns:
        database.execute("ALTER TABLE artworks ADD COLUMN created_at TEXT")
    if "user_id" not in columns:
        database.execute("ALTER TABLE artworks ADD COLUMN user_id INTEGER REFERENCES users(id)")
    database.commit()


def current_user():
    if "user" not in g:
        user_id = session.get("user_id")
        row = None
        if user_id is not None:
            row = get_database().execute(
                "SELECT id, username, display_name, role FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        g.user = dict(row) if row else None
    return g.user


def current_user_id():
    user = current_user()
    return user["id"] if user else -1


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify(error="Please log in first."), 401
            if role and user["role"] != role:
                return jsonify(error=f"Only {role}s can do this."), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def artwork_from_row(row):
    artwork = dict(row)
    try:
        artwork["tags"] = json.loads(artwork["tags"])
    except (TypeError, json.JSONDecodeError):
        artwork["tags"] = []
    artwork["liked"] = bool(artwork.get("liked"))
    return artwork


def fetch_artwork(artwork_id):
    row = get_database().execute(
        f"{ARTWORK_SELECT} WHERE a.id = ?", (current_user_id(), artwork_id)
    ).fetchone()
    return artwork_from_row(row) if row else None


def clean_form_field(name):
    return request.form.get(name, "").strip()


def save_validated_image(upload):
    if not upload or not upload.filename:
        raise ValueError("An image file is required.")

    try:
        upload.stream.seek(0)
        with Image.open(upload.stream) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("The uploaded file is not a valid supported image.")

    extension = ALLOWED_IMAGE_FORMATS.get(image_format)
    if extension is None:
        raise ValueError("Supported image formats are PNG, JPEG, GIF, and WebP.")

    filename = f"{uuid.uuid4().hex}{extension}"
    destination = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    upload.stream.seek(0)
    upload.save(destination)
    return filename, destination


def register_routes(app):
    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/login")
    def login_page():
        return render_template("login.html")

    @app.get("/dashboard")
    def dashboard():
        user = current_user()
        if user is None or user["role"] != "artist":
            return redirect("/login?next=/dashboard")
        return render_template("dashboard.html")

    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)

    @app.post("/api/auth/signup")
    def signup():
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        role = str(payload.get("role", "")).strip()
        display_name = str(payload.get("display_name", "")).strip()[:120] or username

        if not USERNAME_PATTERN.match(username):
            return jsonify(error="Username must be 3-30 letters, numbers, dots or underscores."), 400
        if len(password) < MIN_PASSWORD_LENGTH:
            return jsonify(error=f"Password must be at least {MIN_PASSWORD_LENGTH} characters."), 400
        if role not in ROLES:
            return jsonify(error="Choose whether you are an artist or an art lover."), 400

        database = get_database()
        if database.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone():
            return jsonify(error="That username is taken."), 409
        # Artist names appear on artworks, so two artists may not share one.
        if role == "artist" and database.execute(
            "SELECT 1 FROM users WHERE role = 'artist' AND display_name = ? COLLATE NOCASE",
            (display_name,),
        ).fetchone():
            return jsonify(error="Another artist already uses that name."), 409

        cursor = database.execute(
            "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), display_name, role),
        )
        if role == "artist":
            # Artworks uploaded before accounts existed are claimed by the
            # first artist who registers with the same name.
            database.execute(
                "UPDATE artworks SET user_id = ? WHERE user_id IS NULL AND artist = ? COLLATE NOCASE",
                (cursor.lastrowid, display_name),
            )
        database.commit()

        session.clear()
        session["user_id"] = cursor.lastrowid
        return jsonify(user=current_user()), 201

    @app.post("/api/auth/login")
    def login():
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        row = get_database().execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password):
            return jsonify(error="Incorrect username or password."), 401

        session.clear()
        session["user_id"] = row["id"]
        return jsonify(user=current_user())

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/auth/me")
    def me():
        return jsonify(user=current_user())

    @app.get("/api/artworks")
    def list_artworks():
        rows = get_database().execute(
            f"{ARTWORK_SELECT} ORDER BY a.id DESC", (current_user_id(),)
        ).fetchall()
        return jsonify(artworks=[artwork_from_row(row) for row in rows])

    @app.post("/api/artworks")
    @login_required(role="artist")
    def create_artwork():
        user = current_user()
        fields = {
            "title": clean_form_field("title"),
            "description": clean_form_field("description"),
        }
        missing = [name for name, value in fields.items() if not value]
        if missing:
            return jsonify(error=f"Missing required field(s): {', '.join(missing)}"), 400

        try:
            filename, saved_path = save_validated_image(request.files.get("image"))
        except ValueError as error:
            return jsonify(error=str(error)), 400

        try:
            generated = current_app.extensions["ai_service"].describe_artwork(
                title=fields["title"],
                artist=user["display_name"],
                description=fields["description"],
                image_path=saved_path,
            )
        except GeminiServiceError as error:
            saved_path.unlink(missing_ok=True)
            return jsonify(error=str(error)), error.status_code

        image_url = f"/uploads/{filename}"
        database = get_database()
        cursor = database.execute(
            """
            INSERT INTO artworks
                (title, artist, description, image_url, story, tags, alt_text,
                 created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            """,
            (
                fields["title"],
                user["display_name"],
                fields["description"],
                image_url,
                generated["story"],
                json.dumps(generated["tags"], ensure_ascii=False),
                generated["alt_text"],
                user["id"],
            ),
        )
        database.commit()
        return jsonify(fetch_artwork(cursor.lastrowid)), 201

    @app.get("/api/artworks/<int:artwork_id>")
    def get_artwork(artwork_id):
        artwork = fetch_artwork(artwork_id)
        if artwork is None:
            return jsonify(error="Artwork not found."), 404
        return jsonify(artwork)

    @app.post("/api/artworks/<int:artwork_id>/view")
    def record_view(artwork_id):
        database = get_database()
        cursor = database.execute(
            "UPDATE artworks SET views = views + 1 WHERE id = ?", (artwork_id,)
        )
        database.commit()
        if cursor.rowcount == 0:
            return jsonify(error="Artwork not found."), 404
        return jsonify(views=fetch_artwork(artwork_id)["views"])

    @app.post("/api/artworks/<int:artwork_id>/like")
    @login_required()
    def toggle_like(artwork_id):
        if fetch_artwork(artwork_id) is None:
            return jsonify(error="Artwork not found."), 404

        database = get_database()
        key = (current_user_id(), artwork_id)
        removed = database.execute(
            "DELETE FROM likes WHERE user_id = ? AND artwork_id = ?", key
        ).rowcount
        if not removed:
            database.execute("INSERT INTO likes (user_id, artwork_id) VALUES (?, ?)", key)
        database.commit()

        artwork = fetch_artwork(artwork_id)
        return jsonify(liked=artwork["liked"], likes=artwork["likes"])

    @app.get("/api/dashboard")
    @login_required(role="artist")
    def artist_dashboard():
        user = current_user()
        rows = get_database().execute(
            f"{ARTWORK_SELECT} WHERE a.user_id = ? ORDER BY a.views DESC, a.id DESC",
            (user["id"], user["id"]),
        ).fetchall()
        artworks = [artwork_from_row(row) for row in rows]

        tag_counts = {}
        for artwork in artworks:
            for tag in artwork["tags"]:
                key = tag.lower()
                tag_counts[key] = tag_counts.get(key, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:8]

        total_views = sum(artwork["views"] for artwork in artworks)
        return jsonify(
            artist=user["display_name"],
            stats={
                "artworks": len(artworks),
                "views": total_views,
                "likes": sum(artwork["likes"] for artwork in artworks),
                "average_views": round(total_views / len(artworks), 1) if artworks else 0,
                "top_artwork": artworks[0] if artworks else None,
            },
            top_tags=[{"tag": tag, "count": count} for tag, count in top_tags],
            artworks=artworks,
        )

    @app.post("/api/search")
    def search_artworks():
        payload = request.get_json(silent=True) or {}
        query = payload.get("query", "")
        if not isinstance(query, str) or not query.strip():
            return jsonify(error="A non-empty query is required."), 400

        pattern = f"%{query.strip()}%"
        rows = get_database().execute(
            f"""
            {ARTWORK_SELECT}
            WHERE a.title LIKE ? COLLATE NOCASE
               OR a.artist LIKE ? COLLATE NOCASE
               OR a.description LIKE ? COLLATE NOCASE
               OR a.story LIKE ? COLLATE NOCASE
               OR a.tags LIKE ? COLLATE NOCASE
            ORDER BY a.id DESC
            """,
            (current_user_id(), pattern, pattern, pattern, pattern, pattern),
        ).fetchall()
        return jsonify(artworks=[artwork_from_row(row) for row in rows])

    @app.post("/api/artworks/<int:artwork_id>/chat")
    def chat_about_artwork(artwork_id):
        artwork = fetch_artwork(artwork_id)
        if artwork is None:
            return jsonify(error="Artwork not found."), 404

        payload = request.get_json(silent=True) or {}
        message = payload.get("message", "")
        if not isinstance(message, str) or not message.strip():
            return jsonify(error="A non-empty message is required."), 400

        try:
            reply = current_app.extensions["ai_service"].chat(
                artwork=artwork, message=message.strip()
            )
        except GeminiServiceError as error:
            return jsonify(error=str(error)), error.status_code
        return jsonify(reply=reply)


def register_error_handlers(app):
    @app.errorhandler(RequestEntityTooLarge)
    def image_too_large(_error):
        return jsonify(error="Upload is too large. Maximum size is 10 MB."), 413

    @app.errorhandler(404)
    def api_not_found(error):
        if request.path.startswith("/api/"):
            return jsonify(error="Endpoint not found."), 404
        return error


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"})
