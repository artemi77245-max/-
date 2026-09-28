from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal

from .config import Settings

ActionName = Literal["msi_turbo", "msi_silent", "open_url", "type_text", "talk"]
ALLOWED = {"msi_turbo", "msi_silent", "open_url", "type_text", "talk"}
SCHEMA = {
    "type": "object", "properties": {
        "action": {"type": "string", "enum": sorted(ALLOWED)},
        "reply": {"type": "string"}, "details": {"type": "string"},
    }, "required": ["action", "reply", "details"], "additionalProperties": False,
}
SYSTEM = ("Ты голосовой помощник на Windows. Возвращай строго JSON с action, reply, details. "
          "Говори по-русски. reply — короткая фраза для озвучивания, details — подробный ответ. "
          "Если просят открыть сайт, action=open_url, details должен быть полным https:// URL. "
          "Если просят напечатать текст, action=type_text, details должен содержать точный текст. "
          "msi_turbo / msi_silent только при явной просьбе сменить режим MSI. "
          "В остальных случаях action=talk. Не вставляй в URL или текст лишние пояснения.")


@dataclass(frozen=True)
class Decision:
    action: ActionName
    reply: str
    details: str


def validate(raw: str) -> Decision:
    payload = json.loads(raw)
    if not isinstance(payload, dict) or set(payload) != {"action", "reply", "details"}:
        raise ValueError("Неверный формат ответа ИИ")
    action, reply, details = (payload[k] for k in ("action", "reply", "details"))
    if action not in ALLOWED or not isinstance(reply, str) or not isinstance(details, str):
        raise ValueError("Неверный тип действия или текста")
    if not reply.strip() or len(reply) > 400 or len(details) > 6000:
        raise ValueError("Слишком длинный или пустой ответ")
    return Decision(action, reply.strip(), details.strip())


def ask(prompt: str, settings: Settings) -> Decision:
    if settings.provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Добавь GEMINI_API_KEY в .env")
        from google import genai
        from google.genai import types
        with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=18000)) as client:
            response = client.models.generate_content(
                model=settings.gemini_model, contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM, response_mime_type="application/json",
                    response_json_schema=SCHEMA,
                ),
            )
            return validate(response.text or "")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Добавь OPENAI_API_KEY в .env")
    from openai import OpenAI
    with OpenAI(api_key=key, timeout=18.0, max_retries=1) as client:
        response = client.responses.create(
            model=settings.openai_model, instructions=SYSTEM, input=prompt,
            text={"format": {"type": "json_schema", "name": "assistant_action",
                             "schema": SCHEMA, "strict": True}}, store=False,
        )
        return validate(response.output_text)
