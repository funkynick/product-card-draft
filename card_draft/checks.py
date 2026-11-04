import re

from .models import LlmDraft, ProductInput

TITLE_MAX = 70
DESCRIPTION_MIN = 800
DESCRIPTION_MAX = 1200
QUERIES_MIN = 3
QUERIES_MAX = 5

# Утверждения без чисел, которые в B2B-карточке дорого стоят, если они выдуманы.
CLAIM_STEMS = (
    "гаранти",
    "сертифи",
    "поверк",
    "поверен",
    "поверя",
    "межповер",
    "реестр",
    "взрывозащ",
    "взрывобезоп",
    "искробезоп",
    "доставк",
    "в наличии",
)

# Однобуквенные «с» и «м» не включены: «100 с погрешностью» не должно считаться единицей.
UNITS = (
    "Па", "гПа", "кПа", "МПа", "мПа", "мбар", "бар", "мм", "мкм", "см", "м/с", "кг", "г",
    "В", "мВ", "кВ", "А", "мА", "Вт", "кВт", "ВА", "Гц", "кГц", "МГц", "бит/с", "°C", "%",
    "ч", "мин", "мес", "месяца", "месяцев", "год", "года", "лет",
)  # fmt: skip

# Минус считается знаком, только если перед ним нет цифры или буквы: «0-100», «RS-485».
NUMBER = re.compile(r"(?:(?<![\w.,])[-−–])?\d+(?:[.,]\d+)?")
SPACES = "[    ]"
THOUSANDS = re.compile(rf"(?<![\d.,])\d{{1,3}}(?:{SPACES}\d{{3}})+(?!\d)")
NUMBER_WITH_UNIT = re.compile(
    rf"({NUMBER.pattern})\s*({'|'.join(sorted(UNITS, key=len, reverse=True))})(?![А-Яа-яA-Za-z])"
)
DESIGNATION = re.compile(r"[A-Za-z][A-Za-z0-9-]+|[А-ЯЁ]{2,}[А-ЯЁ0-9-]*")


def source_text(product: ProductInput) -> str:
    """Текст, на который можно опираться. Характеристика без значения фактом не считается."""
    specs = [f"{name} {value}" for name, value in product.specs.items() if value is not None]
    return " ".join(filter(None, [product.name, product.manufacturer, *specs, product.description]))


def check_limits(draft: LlmDraft, product: ProductInput) -> list[str]:
    problems = []
    title_length = len(draft.seo_title.strip())
    if not 0 < title_length <= TITLE_MAX:
        problems.append(f"SEO-заголовок {title_length} символов, норма 1–{TITLE_MAX}")

    # Если фактов меньше нормы, дотянуть до неё можно только домыслами.
    minimum = DESCRIPTION_MIN if _facts_are_enough(product) else 1
    description_length = len(draft.seo_description.strip())
    if not minimum <= description_length <= DESCRIPTION_MAX:
        problems.append(
            f"SEO-описание {description_length} символов, норма "
            f"{DESCRIPTION_MIN}–{DESCRIPTION_MAX}"
        )

    query_count = len({query.strip().lower() for query in draft.search_queries if query.strip()})
    if not QUERIES_MIN <= query_count <= QUERIES_MAX:
        problems.append(f"Разных поисковых запросов {query_count}, норма {QUERIES_MIN}–{QUERIES_MAX}")

    if not draft.suits_for.strip() or not draft.solves.strip():
        problems.append("Блок для менеджера заполнен не полностью")
    return problems


def check_thin_facts(draft: LlmDraft, product: ProductInput) -> list[str]:
    """Нехватка фактов не лечится повторным запросом, но контент-менеджер должен о ней знать."""
    length = len(draft.seo_description.strip())
    if _facts_are_enough(product) or length >= DESCRIPTION_MIN:
        return []
    return [
        f"Фактов не хватает на полное SEO-описание: длина {length} "
        f"при норме {DESCRIPTION_MIN}–{DESCRIPTION_MAX} символов"
    ]


def check_facts(draft: LlmDraft, product: ProductInput) -> list[str]:
    source = source_text(product)
    source = f"{source} {_join_thousands(source)}"
    known_numbers = _numbers(source)
    generated = _join_thousands(
        " ".join(
            [
                draft.seo_title,
                draft.seo_description,
                *draft.search_queries,
                draft.suits_for,
                draft.solves,
            ]
        ),
        known_numbers,
    )

    source_lower = source.lower()
    generated_lower = generated.lower()
    findings = (
        ("Числа", sorted(_numbers(generated) - known_numbers)),
        ("Значения с такими единицами", _mismatched_units(generated, source)),
        ("Обозначения", _unknown_designations(generated, source)),
        (
            "Утверждения",
            [s for s in CLAIM_STEMS if s in generated_lower and s not in source_lower],
        ),
    )
    problems = [
        f"{label}, которых нет во входных данных: {', '.join(unknown)}"
        for label, unknown in findings
        if unknown
    ]
    if any(re.search(r"\d", item) for item in draft.needs_clarification):
        problems.append("В списке для уточнения должны быть только названия, без значений")
    return problems


def _facts_are_enough(product: ProductInput) -> bool:
    return len(source_text(product)) >= DESCRIPTION_MIN


def _join_thousands(text: str, known_numbers: set[str] | None = None) -> str:
    """Склеивает «85 600» в «85600»: везде или только если такое число есть в данных."""

    def join(match: re.Match) -> str:
        joined = re.sub(SPACES, "", match.group())
        return joined if known_numbers is None or joined in known_numbers else match.group()

    return THOUSANDS.sub(join, text)


def _numbers(text: str) -> set[str]:
    return {_normalize_number(match) for match in NUMBER.findall(text)}


def _normalize_number(number: str) -> str:
    number = number.replace(",", ".").replace("−", "-").replace("–", "-")
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return number


def _mismatched_units(generated: str, source: str) -> list[str]:
    source_pairs = _number_units(source)
    # В «от 10 до 30 В» у десятки своей единицы нет, поэтому «10 В» сверить не с чем.
    numbers_with_unit = {number for number, _ in source_pairs}
    return sorted(
        f"{number} {unit}"
        for number, unit in _number_units(generated) - source_pairs
        if number in numbers_with_unit
    )


def _number_units(text: str) -> set[tuple[str, str]]:
    latin_celsius = text.replace("°С", "°C")
    return {
        (_normalize_number(number), unit)
        for number, unit in NUMBER_WITH_UNIT.findall(latin_celsius)
    }


def _unknown_designations(generated: str, source: str) -> list[str]:
    known = _squash(source)
    terms = {_squash(term) for term in DESIGNATION.findall(generated)}
    return sorted(term for term in terms if term not in known)


def _squash(text: str) -> str:
    """Убирает разницу в написании: «RS-485», «RS 485» и «rs485» считаются одним обозначением."""
    return re.sub(rf"-|{SPACES}", "", text).lower()
