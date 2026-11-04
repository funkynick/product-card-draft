from .models import CardResult

STATUS_LABELS = {
    "ready": "Готово к проверке контент-менеджером",
    "needs_review": "Нужна ручная правка: см. раздел «Проблемы»",
    "insufficient_data": "Недостаточно данных для карточки",
}


def render_markdown(card: CardResult) -> str:
    title = f"{card.name}, {card.manufacturer}" if card.manufacturer else card.name
    lines = [f"# {title}", "", f"**Статус:** {STATUS_LABELS[card.status]}", ""]
    lines += _section("Проблемы", card.problems)
    lines += _section("Не хватает во входных данных", card.missing_fields)
    lines += _section("Стоит уточнить у поставщика", card.needs_clarification)

    lines += ["## SEO-заголовок", "", card.seo_title, ""]
    lines += ["## SEO-описание", "", card.seo_description, ""]

    if card.characteristics:
        lines += ["## Характеристики", "", "| Характеристика | Значение |", "|---|---|"]
        lines += [
            f"| {_escape_cell(item.name)} | {_escape_cell(item.value)} |"
            for item in card.characteristics
        ]
        lines.append("")

    lines += _section("Поисковые запросы", card.search_queries)

    lines += ["## Для менеджера", "", f"**Кому подходит:** {card.suits_for}", ""]
    lines += [f"**Какие задачи решает:** {card.solves}", ""]
    return "\n".join(lines)


def _section(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    return [f"## {title}", "", *(f"- {item}" for item in items), ""]


def _escape_cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")
