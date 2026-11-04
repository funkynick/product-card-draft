import pytest

from card_draft.models import LlmDraft, ProductInput

VALID_DESCRIPTION = "Манометр показывающий измеряет избыточное давление. " * 20


@pytest.fixture
def product() -> ProductInput:
    return ProductInput(
        name="Манометр DM 02",
        manufacturer="Манотомь",
        specs={"диапазон измерений": "0–1,6 МПа", "присоединение": "G1/2", "класс точности": 1.5},
        description=VALID_DESCRIPTION,
    )


@pytest.fixture
def draft() -> LlmDraft:
    return LlmDraft(
        seo_title="Манометр DM 02 Манотомь, 0–1,6 МПа",
        seo_description=VALID_DESCRIPTION,
        search_queries=["манометр DM 02", "манометр 1,6 МПа", "манометр G1/2"],
        suits_for="Подходит для контроля избыточного давления.",
        solves="Измеряет избыточное давление.",
        needs_clarification=["диаметр корпуса"],
    )


class FakeClient:
    """Отдаёт заготовленные ответы по очереди: черновик или исключение."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[str] = []

    def generate(self, system: str, user: str) -> LlmDraft:
        self.calls.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def fake_client():
    return FakeClient
