import argparse
import sys
from pathlib import Path

from .llm import ApiClient, LlmError
from .parsing import InputError, parse_product
from .render import render_markdown
from .service import generate_card

EXIT_INPUT_ERROR = 1
EXIT_LLM_ERROR = 3  # 2 занят: так argparse завершается при неверных аргументах


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Черновик карточки товара по JSON с данными прибора")
    parser.add_argument("input", type=Path, help="JSON-файл с данными товара")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="формат результата")
    args = parser.parse_args(argv)

    try:
        product = parse_product(args.input.read_bytes())
    except OSError as exc:
        print(f"Не удалось прочитать файл: {exc.strerror}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except InputError as exc:
        print("\n".join(exc.errors), file=sys.stderr)
        return EXIT_INPUT_ERROR

    try:
        card = generate_card(product, ApiClient())
    except LlmError as exc:
        print(exc, file=sys.stderr)
        return EXIT_LLM_ERROR

    if args.format == "json":
        print(card.model_dump_json(indent=2))
    else:
        print(render_markdown(card))
    return 0
