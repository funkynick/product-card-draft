import pytest

from card_draft.llm import LlmError, LlmOutputError
from card_draft.models import NO_DATA, ProductInput
from card_draft.render import render_markdown
from card_draft.service import MAX_ATTEMPTS, generate_card

INVENTED = {"solves": "Давление до 99 МПа."}
INVENTED_PROBLEM = "Числа, которых нет во входных данных: 99"


def test_ready_card_takes_values_from_input(product, draft, fake_client):
    client = fake_client(draft)

    card = generate_card(product, client)

    assert card.status == "ready"
    assert len(client.calls) == 1
    assert (card.name, card.manufacturer) == ("Манометр DM 02", "Манотомь")
    assert [(item.name, item.value) for item in card.characteristics] == [
        ("диапазон измерений", "0–1,6 МПа"),
        ("присоединение", "G1/2"),
        ("класс точности", "1.5"),
        ("диаметр корпуса", NO_DATA),
    ]


def test_expected_characteristic_is_not_duplicated(product, draft, fake_client):
    product.specs["Диаметр корпуса"] = None

    card = generate_card(product, fake_client(draft))

    names = [item.name.lower() for item in card.characteristics]
    assert names.count("диаметр корпуса") == 1


def test_retries_with_problems_then_succeeds(product, draft, fake_client):
    client = fake_client(draft.model_copy(update=INVENTED), draft)

    card = generate_card(product, client)

    assert card.status == "ready"
    assert INVENTED_PROBLEM in client.calls[1]
    assert INVENTED["solves"] in client.calls[1]


def test_needs_review_after_failed_attempts(product, draft, fake_client):
    client = fake_client(*[draft.model_copy(update=INVENTED)] * MAX_ATTEMPTS)

    card = generate_card(product, client)

    assert card.status == "needs_review"
    assert len(client.calls) == MAX_ATTEMPTS
    assert card.problems == [INVENTED_PROBLEM]


def test_keeps_draft_without_invented_facts_over_later_worse_one(product, draft, fake_client):
    long_title = draft.model_copy(update={"seo_title": "м" * 71})
    invented = draft.model_copy(update=INVENTED)

    card = generate_card(product, fake_client(long_title, invented, invented))

    assert card.seo_title == "м" * 71
    assert card.problems == ["SEO-заголовок 71 символов, норма 1–70"]


def test_keeps_draft_when_retry_fails(product, draft, fake_client):
    client = fake_client(draft.model_copy(update=INVENTED), LlmError("лимит"))

    card = generate_card(product, client)

    assert card.status == "needs_review"
    assert card.problems == [INVENTED_PROBLEM]


def test_first_api_error_is_raised(product, fake_client):
    with pytest.raises(LlmError, match="лимит"):
        generate_card(product, fake_client(LlmError("лимит")))


def test_retries_after_unusable_output(product, draft, fake_client):
    client = fake_client(LlmOutputError("не по схеме"), draft)

    assert generate_card(product, client).status == "ready"
    assert len(client.calls) == 2


def test_raises_when_all_outputs_unusable(product, fake_client):
    client = fake_client(*[LlmOutputError("не по схеме")] * MAX_ATTEMPTS)

    with pytest.raises(LlmOutputError):
        generate_card(product, client)


def test_thin_facts_use_one_attempt_and_need_review(draft, fake_client):
    product = ProductInput(name="Манометр DM 02", manufacturer="Манотомь", description="Измеряет давление.")
    short = draft.model_copy(
        update={
            "seo_title": "Манометр DM 02",
            "seo_description": "Манометр измеряет давление.",
            "search_queries": ["манометр", "манометр DM 02", "измерение давления"],
        }
    )
    client = fake_client(short)

    card = generate_card(product, client)

    assert card.status == "needs_review"
    assert len(client.calls) == 1
    assert "длина 27" in card.problems[0]


def test_empty_spec_is_marked_no_data(product, draft, fake_client):
    product.specs["питание"] = None

    card = generate_card(product, fake_client(draft))

    assert {item.name: item.value for item in card.characteristics}["питание"] == NO_DATA
    assert card.missing_fields == ["значение характеристики «питание»"]


def test_reports_missing_fields(product, draft, fake_client):
    product.manufacturer = None
    product.description = None

    card = generate_card(product, fake_client(draft))

    assert card.missing_fields == ["производитель", "описание"]


def test_no_facts_skips_llm(fake_client):
    client = fake_client()
    product = ProductInput(name="МК110", manufacturer="ОВЕН", specs={"питание": None})

    card = generate_card(product, client)

    assert card.status == "insufficient_data"
    assert client.calls == []
    assert card.seo_description == NO_DATA
    assert card.missing_fields == ["описание", "значение характеристики «питание»"]


def test_markdown_contains_all_sections(product, draft, fake_client):
    product.specs["резьба | тип"] = "G1/2"
    product.specs["выход"] = "0–10 В\n4–20 мА"

    markdown = render_markdown(generate_card(product, fake_client(draft)))

    assert markdown.startswith("# Манометр DM 02, Манотомь\n")
    for heading in ("SEO-заголовок", "SEO-описание", "Характеристики", "Поисковые запросы", "Для менеджера"):
        assert f"## {heading}" in markdown
    assert "резьба \\| тип" in markdown
    assert "| выход | 0–10 В 4–20 мА |" in markdown
