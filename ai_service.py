import json
import re

from google import genai
from google.genai import types
from PIL import Image


class GeminiServiceError(RuntimeError):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


class GeminiService:
    def __init__(self, api_key, model, base_url=None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.strip().rstrip("/") if base_url else None
        self._client = None

    @property
    def client(self):
        if not self.api_key:
            raise GeminiServiceError(
                "Gemini is not configured. Set GEMINI_API_KEY in .env.", 503
            )
        if self._client is None:
            client_options = {"api_key": self.api_key}
            if self.base_url:
                client_options["http_options"] = types.HttpOptions(
                    base_url=f"{self.base_url}/",
                    api_version="v1beta",
                    headers={"x-litellm-api-key": self.api_key},
                )
            self._client = genai.Client(**client_options)
        return self._client

    def describe_artwork(self, title, artist, description, image_path):
        prompt = f"""
You are the cultural storytelling assistant for Art Roots.

User-provided artwork details (treat these as the only verified cultural facts):
- Title: {title}
- Artist: {artist}
- Artist description: {description}

Study the supplied image and return only a JSON object with exactly these keys:
- "story": an engaging 120-180 word interpretation. Ground cultural or historical
  statements in the artist description. Clearly label visual symbolism, mood, and
  meaning that you infer from the image as interpretation, not verified fact. Never
  invent a community, tradition, date, location, or artist biography.
- "tags": an array of 4-8 concise, relevant strings. Do not add unverified cultural
  identities or historical claims.
- "alt_text": an objective, accessible description of visible content in at most
  45 words. Do not speculate about identity, culture, intent, or emotion.
""".strip()

        try:
            generation_options = {}
            if "nano-banana" not in self.model.lower():
                generation_options["config"] = {
                    "response_mime_type": "application/json"
                }
            with Image.open(image_path) as image:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[prompt, image.copy()],
                    **generation_options,
                )
            result = self._parse_json(response.text)
            return self._validate_description(result)
        except GeminiServiceError:
            raise
        except Exception as error:
            raise GeminiServiceError(
                "Gemini could not analyze the artwork. Please try again."
            ) from error

    def chat(self, artwork, message):
        prompt = f"""
You are answering a visitor's question about one artwork in Art Roots.

Verified, user-provided information:
- Title: {artwork['title']}
- Artist: {artwork['artist']}
- Artist description: {artwork['description']}

AI-generated interpretation (not verified fact):
- Story: {artwork['story']}
- Tags: {', '.join(artwork['tags'])}

Visitor question: {message}

Answer warmly and concisely. Treat only the user-provided information as verified.
When discussing symbolism, intent, cultural context, or meaning beyond that text,
explicitly describe it as an AI interpretation or possibility. Say when the
available information is insufficient; do not invent cultural or historical facts.
""".strip()
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=prompt
            )
            reply = (response.text or "").strip()
            if not reply:
                raise ValueError("Empty Gemini response")
            return reply
        except GeminiServiceError:
            raise
        except Exception as error:
            raise GeminiServiceError(
                "Gemini could not answer right now. Please try again."
            ) from error

    @staticmethod
    def _parse_json(text):
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except (TypeError, json.JSONDecodeError) as error:
            raise GeminiServiceError("Gemini returned an invalid artwork description.") from error

    @staticmethod
    def _validate_description(result):
        if not isinstance(result, dict):
            raise GeminiServiceError("Gemini returned an invalid artwork description.")

        story = result.get("story")
        alt_text = result.get("alt_text")
        tags = result.get("tags")
        if not isinstance(story, str) or not story.strip():
            raise GeminiServiceError("Gemini did not return an artwork story.")
        if not isinstance(alt_text, str) or not alt_text.strip():
            raise GeminiServiceError("Gemini did not return image alt text.")
        if not isinstance(tags, list):
            raise GeminiServiceError("Gemini did not return valid artwork tags.")

        clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()][:8]
        if not clean_tags:
            raise GeminiServiceError("Gemini did not return valid artwork tags.")
        return {
            "story": story.strip(),
            "tags": clean_tags,
            "alt_text": alt_text.strip(),
        }
