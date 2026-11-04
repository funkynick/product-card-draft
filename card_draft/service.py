from .checks import check_facts, check_limits, check_thin_facts
from .llm import LlmClient, LlmError, LlmOutputError
from .models import NO_DATA, CardResult, Characteristic, LlmDraft, ProductInput
from .prompts import SYSTEM_PROMPT, build_user_message

MAX_ATTEMPTS = 3

NO_FACTS_DRAFT = LlmDraft(
    seo_title=NO_DATA,
    seo_description=NO_DATA,
    search_queries=[],
    suits_for=NO_DATA,
    solves=NO_DATA,
    needs_clarification=[],
)


def generate_card(product: ProductInput, client: LlmClient) -> CardResult:
    if not _has_facts(product):
        problems = ["Нет ни характеристик, ни описания: модель не вызывалась"]
        return _build_card("insufficient_data", NO_FACTS_DRAFT, product, problems)

    draft, problems = _generate_best_draft(product, client)
    problems = problems + check_thin_facts(draft, product)
    return _build_card("needs_review" if problems else "ready", draft, product, problems)


def _generate_best_draft(product: ProductInput, client: LlmClient) -> tuple[LlmDraft, list[str]]:
    best: LlmDraft | None = None
    best_rank = (0, 0)
    best_problems: list[str] = []
    output_error: LlmOutputError | None = None

    for _ in range(MAX_ATTEMPTS):
        try:
            draft = client.generate(SYSTEM_PROMPT, build_user_message(product, best, best_problems))
        except LlmOutputError as exc:
            output_error = exc
            continue
        except LlmError:
            if best is None:
                raise
            break

        facts = check_facts(draft, product)
        limits = check_limits(draft, product)
        # Выдуманный факт хуже нарушения длины, поэтому факты сравниваются первыми.
        rank = (len(facts), len(limits))
        if best is None or rank <= best_rank:
            best, best_rank, best_problems = draft, rank, facts + limits
        if not best_problems:
            break

    if best is None:
        raise output_error
    return best, best_problems


def _build_card(
    status: str, draft: LlmDraft, product: ProductInput, problems: list[str]
) -> CardResult:
    return CardResult(
        status=status,
        name=product.name,
        manufacturer=product.manufacturer,
        characteristics=build_characteristics(product, draft.needs_clarification),
        missing_fields=find_missing_fields(product),
        problems=problems,
        **draft.model_dump(),
    )


def find_missing_fields(product: ProductInput) -> list[str]:
    missing = []
    if not product.manufacturer:
        missing.append("производитель")
    if not product.specs:
        missing.append("характеристики")
    if not product.description:
        missing.append("описание")
    missing.extend(
        f"значение характеристики «{name}»"
        for name, value in product.specs.items()
        if value is None
    )
    return missing


def build_characteristics(product: ProductInput, expected: list[str]) -> list[Characteristic]:
    """Значения берутся только из входных данных. Ожидаемые, но отсутствующие помечаются."""
    characteristics = [
        Characteristic(name=name, value=NO_DATA if value is None else str(value))
        for name, value in product.specs.items()
    ]
    known = {name.lower() for name in product.specs}
    characteristics.extend(
        Characteristic(name=name, value=NO_DATA) for name in expected if name.lower() not in known
    )
    return characteristics


def _has_facts(product: ProductInput) -> bool:
    return bool(product.description) or any(value is not None for value in product.specs.values())
