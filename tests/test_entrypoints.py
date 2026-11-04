import json

import pytest
from fastapi.testclient import TestClient

from card_draft import cli, web
from card_draft.llm import LlmError


class FailingClient:
    def generate(self, system: str, user: str):
        raise LlmError("Нет соединения с LLM API")


@pytest.fixture
def api(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    return TestClient(web.app)


def test_index_page(api):
    assert "Черновик карточки" in api.get("/").text


def test_api_rejects_bad_json(api):
    response = api.post("/api/card", content="{oops")
    assert response.status_code == 422
    assert "Некорректный JSON" in response.json()["errors"][0]


def test_api_returns_card_without_llm_when_no_facts(api):
    response = api.post("/api/card", json={"name": "МК110", "manufacturer": "ОВЕН"})
    assert response.status_code == 200
    assert response.json()["card"]["status"] == "insufficient_data"
    assert "Недостаточно данных" in response.json()["markdown"]


def test_api_reports_llm_error(api, monkeypatch):
    monkeypatch.setattr(web, "ApiClient", FailingClient)
    response = api.post("/api/card", json={"name": "М", "description": "Текст"})
    assert response.status_code == 502
    assert response.json()["errors"] == ["Нет соединения с LLM API"]


def test_api_returns_card(api, monkeypatch, fake_client, draft):
    monkeypatch.setattr(web, "ApiClient", lambda: fake_client(draft))
    response = api.post(
        "/api/card",
        json={
            "name": "Манометр DM 02",
            "manufacturer": "Манотомь",
            "specs": {"диапазон": "0–1,6 МПа", "присоединение": "G1/2"},
            "description": "Прибор измеряет избыточное давление.",
        },
    )
    assert response.status_code == 200
    assert response.json()["card"]["seo_title"] == draft.seo_title


def test_cli_prints_json(tmp_path, capsys, monkeypatch, fake_client, draft, product):
    monkeypatch.setattr(cli, "ApiClient", lambda: fake_client(draft))
    path = tmp_path / "product.json"
    path.write_text(product.model_dump_json(), encoding="utf-8")

    assert cli.main([str(path), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"


def test_cli_reports_bad_input(tmp_path, capsys):
    path = tmp_path / "product.json"
    path.write_text("{oops", encoding="utf-8")

    assert cli.main([str(path)]) == cli.EXIT_INPUT_ERROR
    assert "Некорректный JSON" in capsys.readouterr().err


def test_cli_reports_missing_file(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope.json")]) == cli.EXIT_INPUT_ERROR
    assert "Не удалось прочитать файл" in capsys.readouterr().err


def test_cli_reports_llm_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "ApiClient", FailingClient)
    path = tmp_path / "product.json"
    path.write_text('{"name": "М", "description": "Текст"}', encoding="utf-8")

    assert cli.main([str(path)]) == cli.EXIT_LLM_ERROR
    assert "Нет соединения" in capsys.readouterr().err
