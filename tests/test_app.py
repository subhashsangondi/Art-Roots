import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ai_service import GeminiService
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

    def signup(self, username="artist1", role="artist", display_name="Test Artist", client=None):
        return (client or self.client).post(
            "/api/auth/signup",
            json={
                "username": username,
                "password": "secret123",
                "role": role,
                "display_name": display_name,
            },
        )

    def create_artwork(self, client=None, artist_field=None):
        data = {
            "title": "Home",
            "description": "The artist describes memories of home.",
            "image": (image_file(), "art.png"),
        }
        if artist_field:
            data["artist"] = artist_field
        return (client or self.client).post(
            "/api/artworks", data=data, content_type="multipart/form-data"
        )

    def test_create_list_get_search_and_image(self):
        self.signup()
        created = self.create_artwork()
        self.assertEqual(created.status_code, 201)
        artwork = created.get_json()
        self.assertEqual(artwork["title"], "Home")
        self.assertEqual(artwork["tags"], ["painting", "roots"])
        self.assertEqual(set(artwork), {
            "id", "title", "artist", "description", "image_url",
            "story", "tags", "alt_text", "views", "created_at",
            "user_id", "likes", "liked"
        })
        self.assertEqual(artwork["views"], 0)

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
        self.signup()
        artwork = self.create_artwork().get_json()
        response = self.client.post(
            f"/api/artworks/{artwork['id']}/chat",
            json={"message": "What does this suggest?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Home", response.get_json()["reply"])

    def test_views_and_dashboard(self):
        self.signup()
        artwork = self.create_artwork().get_json()
        self.create_artwork()
        for _ in range(3):
            response = self.client.post(f"/api/artworks/{artwork['id']}/view")
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["views"], 3)
        self.assertEqual(self.client.post("/api/artworks/999/view").status_code, 404)

        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["artist"], "Test Artist")
        self.assertEqual(dashboard["stats"]["artworks"], 2)
        self.assertEqual(dashboard["stats"]["views"], 3)
        self.assertEqual(dashboard["stats"]["average_views"], 1.5)
        self.assertEqual(dashboard["stats"]["top_artwork"]["id"], artwork["id"])
        self.assertEqual(dashboard["top_tags"][0], {"tag": "painting", "count": 2})

        self.assertEqual(dashboard["stats"]["likes"], 0)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

        other = self.app.test_client()
        self.signup("artist2", display_name="Other Artist", client=other)
        self.assertEqual(other.get("/api/dashboard").get_json()["stats"]["artworks"], 0)

    def test_auth_and_permissions(self):
        anonymous = self.app.test_client()
        self.assertEqual(self.create_artwork(client=anonymous).status_code, 401)
        self.assertEqual(anonymous.get("/api/dashboard").status_code, 401)
        self.assertEqual(anonymous.get("/dashboard").status_code, 302)

        viewer = self.app.test_client()
        self.assertEqual(self.signup("fan", role="viewer", display_name="", client=viewer).status_code, 201)
        self.assertEqual(self.create_artwork(client=viewer).status_code, 403)
        self.assertEqual(viewer.get("/api/dashboard").status_code, 403)

        self.assertEqual(self.signup().status_code, 201)
        self.assertEqual(self.signup().status_code, 409)
        self.assertEqual(self.signup("artist9", display_name="test artist").status_code, 409)
        self.assertEqual(self.signup("x").status_code, 400)

        # The artist name always comes from the account, never the form.
        artwork = self.create_artwork(artist_field="Somebody Else").get_json()
        self.assertEqual(artwork["artist"], "Test Artist")

        liked = viewer.post(f"/api/artworks/{artwork['id']}/like").get_json()
        self.assertEqual(liked, {"liked": True, "likes": 1})
        self.assertEqual(anonymous.post(f"/api/artworks/{artwork['id']}/like").status_code, 401)
        self.assertTrue(viewer.get(f"/api/artworks/{artwork['id']}").get_json()["liked"])
        self.assertEqual(self.client.get("/api/dashboard").get_json()["stats"]["likes"], 1)
        unliked = viewer.post(f"/api/artworks/{artwork['id']}/like").get_json()
        self.assertEqual(unliked, {"liked": False, "likes": 0})

        wrong = anonymous.post("/api/auth/login", json={"username": "artist1", "password": "nope"})
        self.assertEqual(wrong.status_code, 401)
        login = anonymous.post("/api/auth/login", json={"username": "artist1", "password": "secret123"})
        self.assertEqual(login.get_json()["user"]["role"], "artist")
        anonymous.post("/api/auth/logout")
        self.assertIsNone(anonymous.get("/api/auth/me").get_json()["user"])

    def test_validation_and_not_found(self):
        self.signup()
        missing = self.client.post("/api/artworks", data={})
        self.assertEqual(missing.status_code, 400)

        invalid_image = self.client.post(
            "/api/artworks",
            data={
                "title": "Bad",
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


class GeminiServiceTest(unittest.TestCase):
    @patch("ai_service.genai.Client")
    def test_nexus_base_url_and_auth_header(self, client_class):
        service = GeminiService(
            api_key="test-key",
            model="test-model",
            base_url="https://nexus.example/",
        )

        service.client

        options = client_class.call_args.kwargs["http_options"]
        self.assertEqual(options.base_url, "https://nexus.example/")
        self.assertEqual(options.api_version, "v1beta")
        self.assertEqual(options.headers["x-litellm-api-key"], "test-key")

    def test_nano_banana_resizes_large_image_and_avoids_json_mode(self):
        class FakeResponse:
            text = '{"story":"Story","tags":["blue"],"alt_text":"Blue image"}'

        class FakeModels:
            def __init__(self):
                self.image_size = None
                self.options = None

            def generate_content(self, model, contents, **options):
                self.image_size = contents[1].size
                self.options = options
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.models = FakeModels()

        service = GeminiService(
            api_key="test-key",
            model="nano-banana",
            base_url="https://nexus.example",
        )
        service._client = FakeClient()
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "large.jpg"
            Image.new("RGB", (3840, 2160), "blue").save(image_path)
            result = service.describe_artwork(
                title="Blue",
                artist="Artist",
                description="A blue study.",
                image_path=image_path,
            )

        self.assertEqual(service._client.models.image_size, (512, 288))
        self.assertEqual(service._client.models.options, {})
        self.assertEqual(result["tags"], ["blue"])


    def test_busy_model_falls_back_immediately(self):
        from google.genai import errors

        busy = {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}

        class FakeModels:
            def __init__(self):
                self.calls = []

            def generate_content(self, model, contents, **options):
                self.calls.append(model)
                if model == "primary":
                    raise errors.ServerError(503, busy)
                return type("Response", (), {"text": "A reply"})()

        service = GeminiService(api_key="k", model="primary", fallback_models=["backup"])
        service._client = type("Client", (), {"models": FakeModels()})()

        self.assertEqual(service.chat(
            artwork={"title": "T", "artist": "A", "description": "D", "story": "S", "tags": []},
            message="Hi",
        ), "A reply")
        self.assertEqual(service._client.models.calls, ["primary", "backup"])

        service.fallback_models = []
        with self.assertRaisesRegex(Exception, "very busy"):
            service.chat(
                artwork={"title": "T", "artist": "A", "description": "D", "story": "S", "tags": []},
                message="Hi",
            )


if __name__ == "__main__":
    unittest.main()
