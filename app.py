import json
import os
import sqlite3
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, current_app, g, jsonify, render_template, request, send_from_directory
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge

from ai_service import GeminiService, GeminiServiceError


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

ALLOWED_IMAGE_FORMATS = {
    "GIF": ".gif",
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=str(BASE_DIR / "art_roots.db"),
        UPLOAD_FOLDER=str(BASE_DIR / "uploads"),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        GEMINI_API_KEY=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        GEMINI_BASE_URL=os.getenv("GEMINI_BASE_URL")
        or os.getenv("NEXUS_BASE_URL"),
        GEMINI_MODEL=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    app.extensions["ai_service"] = GeminiService(
        api_key=app.config.get("GEMINI_API_KEY"),
        base_url=app.config.get("GEMINI_BASE_URL"),
        model=app.config["GEMINI_MODEL"],
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
    database.commit()


def artwork_from_row(row):
    artwork = dict(row)
    try:
        artwork["tags"] = json.loads(artwork["tags"])
    except (TypeError, json.JSONDecodeError):
        artwork["tags"] = []
    return artwork


def fetch_artwork(artwork_id):
    row = get_database().execute(
        "SELECT * FROM artworks WHERE id = ?", (artwork_id,)
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

    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)

    @app.get("/api/artworks")
    def list_artworks():
        rows = get_database().execute(
            "SELECT * FROM artworks ORDER BY id DESC"
        ).fetchall()
        return jsonify(artworks=[artwork_from_row(row) for row in rows])

    @app.post("/api/artworks")
    def create_artwork():
        fields = {
            "title": clean_form_field("title"),
            "artist": clean_form_field("artist"),
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
                artist=fields["artist"],
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
                (title, artist, description, image_url, story, tags, alt_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["title"],
                fields["artist"],
                fields["description"],
                image_url,
                generated["story"],
                json.dumps(generated["tags"], ensure_ascii=False),
                generated["alt_text"],
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

    @app.post("/api/search")
    def search_artworks():
        payload = request.get_json(silent=True) or {}
        query = payload.get("query", "")
        if not isinstance(query, str) or not query.strip():
            return jsonify(error="A non-empty query is required."), 400

        pattern = f"%{query.strip()}%"
        rows = get_database().execute(
            """
            SELECT * FROM artworks
            WHERE title LIKE ? COLLATE NOCASE
               OR artist LIKE ? COLLATE NOCASE
               OR description LIKE ? COLLATE NOCASE
               OR story LIKE ? COLLATE NOCASE
               OR tags LIKE ? COLLATE NOCASE
            ORDER BY id DESC
            """,
            (pattern, pattern, pattern, pattern, pattern),
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
