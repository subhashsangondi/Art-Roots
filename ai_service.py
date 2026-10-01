import json
import logging
import re
import time

from google import genai
from google.genai import errors, types
from PIL import Image


MAX_ANALYSIS_DIMENSION = 512
GEMINI_TIMEOUT_MS = 90_000
# Gemini returns these when a model is overloaded or rate limited; they are
# usually temporary, so we retry and then fall back to another model.
RETRYABLE_STATUS_CODES = {429, 500, 503, 504}
ATTEMPTS_PER_MODEL = 2
RETRY_DELAY_SECONDS = 1.5

logger = logging.getLogger(__name__)


class GeminiServiceError(RuntimeError):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


class GeminiService:
    def __init__(self, api_key, model, base_url=None, fallback_models=()):
        self.api_key = api_key
        self.model = model
        self.fallback_models = [name for name in fallback_models if name and name != model]
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
                    timeout=GEMINI_TIMEOUT_MS,
                )
            else:
                client_options["http_options"] = types.HttpOptions(
                    timeout=GEMINI_TIMEOUT_MS
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
            with Image.open(image_path) as image:
                image.thumbnail(
                    (MAX_ANALYSIS_DIMENSION, MAX_ANALYSIS_DIMENSION),
                    Image.Resampling.LANCZOS,
                )
                analysis_image = image.copy()
            response = self._generate([prompt, analysis_image], json_output=True)
            result = self._parse_json(response.text)
            return self._validate_description(result)
        except GeminiServiceError:
            raise
        except Exception as error:
            logger.exception("Artwork analysis failed")
            raise GeminiServiceError(self._friendly_message(
                error, "Gemini could not analyze the artwork. Please try again."
            )) from error

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
            response = self._generate(prompt)
            reply = (response.text or "").strip()
            if not reply:
                raise ValueError("Empty Gemini response")
            return reply
        except GeminiServiceError:
            raise
        except Exception as error:
            logger.exception("Artwork chat failed")
            raise GeminiServiceError(self._friendly_message(
                error, "Gemini could not answer right now. Please try again."
            )) from error

    def _generate(self, contents, json_output=False):
        """Call Gemini, retrying busy models and falling back to the next one."""
        last_error = None
        for model in [self.model, *self.fallback_models]:
            options = {}
            if json_output and "nano-banana" not in model.lower():
                options["config"] = {"response_mime_type": "application/json"}
            for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
                try:
                    return self.client.models.generate_content(
                        model=model, contents=contents, **options
                    )
                except errors.APIError as error:
                    last_error = error
                    logger.warning(
                        "Gemini model %s failed (attempt %d): %s %s",
                        model, attempt, error.code, error.status,
                    )
                    if error.code == 404:
                        break  # model not available to this key; try the next one
                    if error.code not in RETRYABLE_STATUS_CODES:
                        raise
                    if attempt < ATTEMPTS_PER_MODEL:
                        time.sleep(RETRY_DELAY_SECONDS)
        raise last_error

    @staticmethod
    def _friendly_message(error, default):
        if isinstance(error, errors.APIError) and error.code in RETRYABLE_STATUS_CODES:
            return "Gemini is very busy right now. Please wait a few seconds and try again."
        return default

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
