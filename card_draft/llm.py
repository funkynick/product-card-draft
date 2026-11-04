import os
from typing import Protocol

import openai
from dotenv import load_dotenv
from pydantic import ValidationError

from .models import LlmDraft

load_dotenv()

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 120
SDK_RETRIES = 1

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "card_draft", "strict": True, "schema": LlmDraft.model_json_schema()},
}


class LlmError(Exception):
    pass


class LlmOutputError(LlmError):
    """Ответ получен, но им нельзя воспользоваться: повторный запрос может помочь."""


class LlmClient(Protocol):
    def generate(self, system: str, user: str) -> LlmDraft: ...


class ApiClient:
    """Клиент для любого OpenAI-совместимого API: OpenRouter, OpenAI, Ollama, vLLM."""

    def __init__(self, client: openai.OpenAI | None = None):
        self._model = os.environ.get("LLM_MODEL", "")
        self._api_key = os.environ.get("LLM_API_KEY", "")
        self._client = client or openai.OpenAI(
            # SDK не принимает пустой ключ, а generate сообщает о нём понятнее.
            api_key=self._api_key or "not-set",
            base_url=os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL,
            timeout=TIMEOUT_SECONDS,
            max_retries=SDK_RETRIES,
        )

    def generate(self, system: str, user: str) -> LlmDraft:
        if not self._api_key or not self._model:
            raise LlmError("Не заданы LLM_API_KEY и LLM_MODEL: заполните файл .env")

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format=RESPONSE_FORMAT,
            )
        except openai.AuthenticationError:
            raise LlmError("LLM API отклонил ключ: проверьте LLM_API_KEY") from None
        except openai.PermissionDeniedError:
            raise LlmError("У ключа нет доступа к этой модели или API") from None
        except openai.NotFoundError:
            raise LlmError(f"Модель {self._model} не найдена: проверьте LLM_MODEL") from None
        except openai.RateLimitError:
            raise LlmError("Превышен лимит запросов к LLM API, повторите позже") from None
        except openai.APIStatusError as exc:
            raise LlmError(f"LLM API вернул ошибку {exc.status_code}") from None
        except openai.APIConnectionError:
            raise LlmError("Нет соединения с LLM API") from None
        except ValueError:
            # Код 200, но тело не JSON: например, HTML от промежуточного прокси.
            raise LlmOutputError("LLM API вернул ответ не в формате JSON") from None

        return _parse_response(response)


def _parse_response(response) -> LlmDraft:
    # OpenRouter может вернуть ошибку провайдера с кодом 200 и без choices,
    # а SDK не проверяет структуру ответа.
    choices = getattr(response, "choices", None)
    message = getattr(choices[0], "message", None) if choices else None
    if message is None:
        raise LlmOutputError("LLM API вернул пустой ответ")

    if message.refusal:
        raise LlmError("Модель отказалась обрабатывать запрос")
    if choices[0].finish_reason == "length" or not message.content:
        raise LlmOutputError("Модель не вернула полный ответ")

    try:
        return LlmDraft.model_validate_json(message.content)
    except ValidationError:
        raise LlmOutputError("Модель вернула ответ не по схеме") from None
