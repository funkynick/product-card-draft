import json

from pydantic import ValidationError

from .models import ProductInput


class InputError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors


def parse_product(text: str | bytes) -> ProductInput:
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except UnicodeDecodeError:
        raise InputError(["Файл не в кодировке UTF-8"]) from None
    except json.JSONDecodeError as exc:
        raise InputError(
            [f"Некорректный JSON: строка {exc.lineno}, столбец {exc.colno}: {exc.msg}"]
        ) from None
    except (ValueError, RecursionError):
        raise InputError(["Некорректный JSON: недопустимое значение или слишком большая вложенность"]) from None

    if not isinstance(data, dict):
        raise InputError(["Ожидается JSON-объект с данными одного товара"])

    try:
        return ProductInput.model_validate(data)
    except ValidationError as exc:
        # Ошибка в значении spec приходит отдельно по каждому допустимому типу.
        messages = dict.fromkeys(_format_error(error) for error in exc.errors())
        raise InputError(list(messages)) from None


def _reject_constant(constant: str) -> None:
    raise ValueError(f"{constant} не является числом")


def _format_error(error: dict) -> str:
    field = ".".join(str(part) for part in error["loc"][:2])
    if field == "name":
        return "Поле name обязательно и не может быть пустым"
    if error["type"] == "extra_forbidden":
        return f"Неизвестное поле {field}: допустимы name, manufacturer, specs, description"
    if field.startswith("specs."):
        return f"Значение {field} должно быть строкой или числом"
    return f"Поле {field}: неверный тип данных"
