import pytest

from card_draft.checks import check_facts, check_limits, check_thin_facts
from card_draft.models import LlmDraft, ProductInput


def text_draft(text: str) -> LlmDraft:
    """Черновик, где проверяется только один фрагмент текста."""
    return LlmDraft(
        seo_title="",
        seo_description="",
        search_queries=[],
        suits_for="",
        solves=text,
        needs_clarification=[],
    )


def test_valid_draft_has_no_problems(draft, product):
    assert check_limits(draft, product) == []
    assert check_facts(draft, product) == []
    assert check_thin_facts(draft, product) == []


def test_flags_long_title(draft, product):
    draft.seo_title = "м" * 71
    assert check_limits(draft, product) == ["SEO-заголовок 71 символов, норма 1–70"]


def test_flags_empty_fields(draft, product):
    draft.seo_title = " "
    draft.solves = ""
    assert check_limits(draft, product) == [
        "SEO-заголовок 0 символов, норма 1–70",
        "Блок для менеджера заполнен не полностью",
    ]


def test_flags_short_description_when_facts_are_enough(draft, product):
    draft.seo_description = "короткий текст"
    assert "SEO-описание 14 символов" in check_limits(draft, product)[0]
    assert check_thin_facts(draft, product) == []


def test_thin_facts_are_reported_without_retry(draft):
    product = ProductInput(name="Манометр", description="Измеряет давление.")
    draft.seo_description = "короткий текст"
    assert check_limits(draft, product) == []
    assert "длина 14" in check_thin_facts(draft, product)[0]


def test_flags_long_description_even_with_thin_facts(draft):
    draft.seo_description = "м" * 1201
    problems = check_limits(draft, ProductInput(name="Манометр"))
    assert problems == ["SEO-описание 1201 символов, норма 800–1200"]


@pytest.mark.parametrize(
    "queries",
    [["манометр"], ["манометр", "манометр ", "Манометр"], ["манометр", "", "  "]],
)
def test_counts_only_distinct_queries(draft, product, queries):
    draft.search_queries = queries
    assert check_limits(draft, product) == ["Разных поисковых запросов 1, норма 3–5"]


def test_flags_invented_number(draft, product):
    draft.solves = "Измеряет давление до 2,5 МПа."
    assert check_facts(draft, product) == ["Числа, которых нет во входных данных: 2.5"]


def test_accepts_number_format_variants(draft, product):
    product.specs["скорость"] = "85600 бит/с"
    draft.solves = "Диапазон до 1.6 МПа, класс 1,50, скорость 85 600 бит/с."
    assert check_facts(draft, product) == []


def test_does_not_join_neighbouring_numbers():
    product = ProductInput(name="testo 510", specs={"Диапазон": "100 гПа"})
    assert check_facts(text_draft("Модель 510 100 гПа."), product) == []


def test_flags_changed_sign():
    product = ProductInput(name="Модем", specs={"Температура": "от -30 до +70 °C"})
    assert check_facts(text_draft("Работает от +30 до +70 °C."), product) == [
        "Числа, которых нет во входных данных: 30"
    ]


@pytest.mark.parametrize("text", ["от -30 °C", "от −30 °C", "от –30 °C", "модель 0-30"])
def test_accepts_minus_spellings_and_ranges(text):
    product = ProductInput(name="Модем 0", specs={"Температура": "от -30 до +70 °C", "Шкала": "30"})
    assert check_facts(text_draft(text), product) == []


@pytest.mark.parametrize(
    ("source", "text", "expected"),
    [
        ("0 ... 100 гПа", "Диапазон 0–100 Па.", "100 Па"),
        ("0–1,6 МПа", "Диапазон 0–1,6 мПа.", "1.6 мПа"),
        ("не менее 8 лет", "Служит 8 месяцев.", "8 месяцев"),
    ],
)
def test_flags_wrong_unit(source, text, expected):
    product = ProductInput(name="Прибор", specs={"Параметр": source})
    assert check_facts(text_draft(text), product) == [
        f"Значения с такими единицами, которых нет во входных данных: {expected}"
    ]


def test_accepts_range_start_without_own_unit():
    product = ProductInput(name="Модем", specs={"Питание": "от 10 до 30 В"})
    assert check_facts(text_draft("Питание от 10 В до 30 В."), product) == []


def test_accepts_cyrillic_celsius():
    product = ProductInput(name="Модем", specs={"Температура": "до +70 °C"})
    assert check_facts(text_draft("Работает до +70 °С."), product) == []


def test_flags_invented_designations(draft, product):
    draft.suits_for = "Подходит для систем с Modbus по ГОСТ."
    assert check_facts(draft, product) == [
        "Обозначения, которых нет во входных данных: modbus, гост"
    ]


@pytest.mark.parametrize(
    ("source", "text"),
    [
        ("Интерфейс RS-485.", "Для оборудования с rs485."),
        ("Интерфейс RS-485.", "Для оборудования с RS 485."),
        ("по гост 2405", "По ГОСТ 2405."),
        ("Назначение:\nRS-485 и\tGSM", "Работает с RS-485 и GSM."),
    ],
)
def test_accepts_designation_variants(source, text):
    assert check_facts(text_draft(text), ProductInput(name="Модем", description=source)) == []


def test_field_names_are_not_allowed_terms(draft, product):
    draft.solves = "Поле description и specs."
    assert check_facts(draft, product) == [
        "Обозначения, которых нет во входных данных: description, specs"
    ]


@pytest.mark.parametrize(
    ("text", "stem"),
    [
        ("Действует гарантия.", "гаранти"),
        ("Взрывозащищённое исполнение.", "взрывозащ"),
        ("Взрывобезопасное исполнение.", "взрывобезоп"),
        ("Внесён в Государственный реестр.", "реестр"),
        ("Прибор поверен.", "поверен"),
    ],
)
def test_flags_invented_claims(draft, product, text, stem):
    draft.solves = text
    assert check_facts(draft, product) == [f"Утверждения, которых нет во входных данных: {stem}"]


def test_accepts_claim_present_in_input(draft, product):
    product.description = "Гарантия на прибор указана в паспорте."
    draft.solves = "Гарантия указана в паспорте."
    assert check_facts(draft, product) == []


def test_word_surface_is_not_a_verification_claim(draft, product):
    draft.solves = "Крепится на поверхности."
    assert check_facts(draft, product) == []


def test_spec_without_value_does_not_allow_claim():
    product = ProductInput(name="Модем", specs={"Гарантия": None, "Modbus": None, "Масса": "2 кг"})
    assert check_facts(text_draft("Действует гарантия, есть Modbus."), product) == [
        "Обозначения, которых нет во входных данных: modbus",
        "Утверждения, которых нет во входных данных: гаранти",
    ]


def test_clarification_list_must_not_contain_values(draft, product):
    draft.needs_clarification = ["гарантия 5 лет"]
    assert check_facts(draft, product) == [
        "В списке для уточнения должны быть только названия, без значений"
    ]
