"""The one place that talks to a language model - Google's Gemini.

Everything else asks for "this prompt (and maybe this audio), answered as this
shape" and gets back a checked object. Swapping provider means rewriting only
this file.
"""

from pydantic import BaseModel

from ..config import settings


class AIUnavailable(RuntimeError):
    """No key, no package, or the service could not answer."""


def generate(system: str, prompt: str, shape: type[BaseModel],
             audio: bytes | None = None, audio_type: str = "audio/mp3") -> BaseModel:
    """Ask the model, and get its answer back as an instance of `shape`.

    Structured output: the model is told the exact JSON shape (field names,
    types) to answer in, and the reply is parsed and validated against it, so
    the calling code never has to pick a sentence apart.

    `audio` is sent alongside the prompt: Gemini listens to it as well as
    reading. It goes first and the instructions after, as Google advises for
    large inputs.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise AIUnavailable("the google-genai package is not installed") from error

    try:
        client = genai.Client()  # reads GEMINI_API_KEY from the environment
    except Exception as error:  # noqa: BLE001 - missing key surfaces here
        raise AIUnavailable(f"no Gemini API key ({error})") from error

    contents = [types.Part.from_bytes(data=audio, mime_type=audio_type), prompt] if audio else prompt
    try:
        response = client.models.generate_content(
            model=settings.llm_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                # Temperature left at its default: Google warns that lowering
                # it on Gemini 3 models can cause looping and worse answers.
                # Thinking at "high" (also the default), because this task
                # is judgment-heavy: listening, comparing, deciding.
                thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
                response_mime_type="application/json",
                response_schema=shape,
            ),
        )
    except Exception as error:  # noqa: BLE001 - network, quota, refusal...
        raise AIUnavailable(f"Gemini could not answer: {error}") from error

    parsed = response.parsed
    if isinstance(parsed, shape):
        return parsed
    if not response.text:
        raise AIUnavailable("Gemini returned an empty answer")
    return shape.model_validate_json(response.text)
