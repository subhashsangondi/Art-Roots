import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app import create_app


class FakeAIService:
    def describe_artwork(self, **_kwargs):
        return {
            "story": "An AI interpretation grounded in the artist's description.",
            "tags": ["painting", "roots"],
            "alt_text": "A square field of warm red color.",
        }

    def chat(self, artwork, message):
        return f"About {artwork['title']}: {message}"


def image_file():
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(stream, format="PNG")
    stream.seek(0)
    return stream


class ArtworkAPITest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": str(root / "test.db"),
                "UPLOAD_FOLDER": str(root / "uploads"),
                "GEMINI_API_KEY": "test-only-placeholder",
            }
        )
        self.app.extensions["ai_service"] = FakeAIService()
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_artwork(self):
        return self.client.post(
            "/api/artworks",
            data={
                "title": "Home",
                "artist": "Test Artist",
                "description": "The artist describes memories of home.",
                "image": (image_file(), "art.png"),
            },
            content_type="multipart/form-data",
        )

    def test_create_list_get_search_and_image(self):
        created = self.create_artwork()
        self.assertEqual(created.status_code, 201)
        artwork = created.get_json()
        self.assertEqual(artwork["title"], "Home")
        self.assertEqual(artwork["tags"], ["painting", "roots"])
        self.assertEqual(set(artwork), {
            "id", "title", "artist", "description", "image_url",
            "story", "tags", "alt_text"
        })

        listed = self.client.get("/api/artworks")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["artworks"]), 1)

        fetched = self.client.get(f"/api/artworks/{artwork['id']}")
        self.assertEqual(fetched.get_json()["artist"], "Test Artist")

        searched = self.client.post("/api/search", json={"query": "memories"})
        self.assertEqual(len(searched.get_json()["artworks"]), 1)

        image_response = self.client.get(artwork["image_url"])
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.mimetype, "image/png")
        image_response.close()

    def test_chat(self):
        artwork = self.create_artwork().get_json()
        response = self.client.post(
            f"/api/artworks/{artwork['id']}/chat",
            json={"message": "What does this suggest?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Home", response.get_json()["reply"])

    def test_validation_and_not_found(self):
        missing = self.client.post("/api/artworks", data={})
        self.assertEqual(missing.status_code, 400)

        invalid_image = self.client.post(
            "/api/artworks",
            data={
                "title": "Bad",
                "artist": "Artist",
                "description": "Description",
                "image": (io.BytesIO(b"not an image"), "bad.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid_image.status_code, 400)

        self.assertEqual(self.client.get("/api/artworks/999").status_code, 404)
        self.assertEqual(
            self.client.post("/api/search", json={"query": ""}).status_code, 400
        )
        self.assertEqual(
            self.client.post("/api/artworks/999/chat", json={"message": "Hi"}).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
