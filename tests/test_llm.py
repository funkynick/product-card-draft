import json

import httpx
import openai
import pytest

from card_draft.llm import ApiClient, LlmError, LlmOutputError


@pytest.fixture
def make_client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    def factory(handler):
        return ApiClient(
            openai.OpenAI(
                api_key="test-key",
                base_url="http://llm.test/v1",
                max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            )
        )

    return factory


def completion(content: str | None, finish_reason: str = "stop", refusal: str | None = None) -> dict:
    message = {"role": "assistant", "content": content, "refusal": refusal}
    return {"choices": [{"index": 0, "finish_reason": finish_reason, "message": message}]}


def test_returns_parsed_draft(make_client, draft):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion(draft.model_dump_json()))

    result = make_client(handler).generate("system", "user")

    assert result == draft
    assert requests[0]["model"] == "test-model"
    assert requests[0]["messages"][0] == {"role": "system", "content": "system"}
    assert requests[0]["response_format"]["json_schema"]["schema"]["additionalProperties"] is False


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "отклонил ключ"),
        (403, "нет доступа"),
        (404, "не найдена"),
        (429, "лимит"),
        (402, "ошибку 402"),
        (500, "ошибку 500"),
    ],
)
def test_maps_api_errors(make_client, status, expected):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "x"}})

    with pytest.raises(LlmError, match=expected) as exc_info:
        make_client(handler).generate("system", "user")
    assert not isinstance(exc_info.value, LlmOutputError)


def test_maps_connection_error(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(LlmError, match="соединения"):
        make_client(handler).generate("system", "user")


def test_refusal_is_not_retryable(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion(None, refusal="нет"))

    with pytest.raises(LlmError, match="отказалась") as exc_info:
        make_client(handler).generate("system", "user")
    assert not isinstance(exc_info.value, LlmOutputError)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (completion('{"seo_title": "обрезано', finish_reason="length"), "не вернула полный"),
        (completion(None), "не вернула полный"),
        (completion('{"seo_title": "только заголовок"}'), "не по схеме"),
        (completion("просто текст"), "не по схеме"),
        ({"choices": []}, "пустой ответ"),
        ({"error": {"message": "provider failed"}}, "пустой ответ"),
        ({"choices": [{"index": 0}]}, "пустой ответ"),
        ({"choices": [{"message": None}]}, "пустой ответ"),
        ([1, 2], "пустой ответ"),
    ],
)
def test_unusable_output_is_retryable(make_client, body, expected):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(LlmOutputError, match=expected):
        make_client(handler).generate("system", "user")


@pytest.mark.parametrize(
    ("content", "content_type"),
    [("<html>Bad gateway</html>", "text/html"), ("{oops", "application/json")],
)
def test_non_json_body_is_retryable(make_client, content, content_type):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-type": content_type})

    with pytest.raises(LlmOutputError):
        make_client(handler).generate("system", "user")


def test_requires_key_and_model(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(LlmError, match="LLM_API_KEY"):
        ApiClient().generate("system", "user")
