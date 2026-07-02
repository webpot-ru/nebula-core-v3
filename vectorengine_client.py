import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "https://api.vectorengine.ai"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_IMAGE_TIMEOUT_SECONDS = 300
DEFAULT_GEMINI_RETRIES = int(os.environ.get("VECTORENGINE_GEMINI_RETRIES", "2"))


class VectorEngineError(RuntimeError):
    pass


def load_dotenv_file(path: str | Path | None) -> bool:
    if not path:
        return False
    env_path = Path(path)
    if not env_path.exists():
        return False

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        raw_key, raw_value = line.split("=", 1)
        key = raw_key.replace("export ", "").strip()
        if not key or key in os.environ:
            continue
        value = raw_value.strip()
        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]
        os.environ[key] = value
    return True


def get_api_key() -> tuple[str, str]:
    if os.environ.get("VECTORENGINE_API_KEY"):
        return "VECTORENGINE_API_KEY", os.environ["VECTORENGINE_API_KEY"]
    if os.environ.get("VECTOR_ENGINE_API_KEY"):
        return "VECTOR_ENGINE_API_KEY", os.environ["VECTOR_ENGINE_API_KEY"]
    raise VectorEngineError("Missing VECTORENGINE_API_KEY or VECTOR_ENGINE_API_KEY.")


def clean_base_url(value: str | None = None) -> str:
    return (value or os.environ.get("VECTORENGINE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def safe_response_text(response: requests.Response, limit: int = 800) -> str:
    text = response.text.strip()
    try:
        data = response.json()
        text = data.get("error", {}).get("message") or data.get("message") or text
    except ValueError:
        pass
    return text[:limit] + ("..." if len(text) > limit else "")


def extract_text_from_gemini_response(data: dict[str, Any]) -> str:
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts if not part.get("thought"))


def first_balanced_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def parse_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise VectorEngineError("VectorEngine returned empty text.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        extracted = first_balanced_json_object(raw)
        if not extracted:
            raise VectorEngineError(f"VectorEngine did not return JSON: {raw[:500]}")
        return json.loads(extracted)


def call_gemini_json(
    *,
    prompt: str,
    model: str | None = None,
    system_instruction: str = "Return strict JSON only. Do not use Markdown.",
    temperature: float = 0.35,
    max_output_tokens: int = 1800,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int | None = None,
) -> dict[str, Any]:
    if not prompt:
        raise VectorEngineError("VectorEngine Gemini prompt is required.")

    _, api_key = get_api_key()
    active_model = model or os.environ.get("VECTORENGINE_GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
    endpoint = (
        f"{clean_base_url()}/v1beta/models/{active_model}:generateContent"
        f"?key={api_key}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": temperature,
            "topP": 1,
            "maxOutputTokens": max_output_tokens,
        },
    }
    attempts = max(1, int(DEFAULT_GEMINI_RETRIES if retries is None else retries) + 1)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=timeout_seconds,
            )
            if not response.ok:
                raise VectorEngineError(
                    f"VectorEngine Gemini HTTP {response.status_code}: {safe_response_text(response)}"
                )

            try:
                response_data = response.json()
            except ValueError as exc:
                raise VectorEngineError(f"VectorEngine Gemini returned non-JSON: {response.text[:500]}") from exc

            return parse_json_object(extract_text_from_gemini_response(response_data))
        except (requests.RequestException, VectorEngineError) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(min(20, 3 * attempt))

    raise VectorEngineError(str(last_error or "VectorEngine Gemini request failed."))


def call_image_generation(
    *,
    prompt: str,
    output_path: str | Path,
    model: str | None = None,
    size: str = "1536x864",
    timeout_seconds: int = DEFAULT_IMAGE_TIMEOUT_SECONDS,
    retries: int = 2,
) -> Path:
    if not prompt:
        raise VectorEngineError("VectorEngine image prompt is required.")

    _, api_key = get_api_key()
    active_model = model or os.environ.get("VECTORENGINE_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL
    endpoint = f"{clean_base_url()}/v1/images/generations"
    output = Path(output_path)
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            response = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": active_model, "prompt": prompt, "size": size, "n": 1},
                timeout=timeout_seconds,
            )
            if not response.ok:
                raise VectorEngineError(
                    f"VectorEngine image HTTP {response.status_code}: {safe_response_text(response)}"
                )
            data = response.json()
            first = (data.get("data") or [None])[0]
            if not first:
                raise VectorEngineError(f"VectorEngine image response missing data[0]: {str(data)[:500]}")
            if first.get("b64_json"):
                output.write_bytes(base64.b64decode(first["b64_json"]))
                return output
            if first.get("url"):
                image_response = requests.get(first["url"], timeout=timeout_seconds)
                if not image_response.ok:
                    raise VectorEngineError(f"VectorEngine image URL HTTP {image_response.status_code}")
                output.write_bytes(image_response.content)
                return output
            raise VectorEngineError(f"VectorEngine image response has no b64_json/url: {str(first)[:500]}")
        except (requests.RequestException, VectorEngineError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(min(30, 5 * (attempt + 1)))

    raise VectorEngineError(str(last_error or "VectorEngine image generation failed."))
