import pytest

from card_draft.parsing import InputError, parse_product


def test_parses_valid_product():
    product = parse_product('{"name": " Манометр ", "specs": {"класс точности": 1.5}}')
    assert product.name == "Манометр"
    assert product.specs == {"класс точности": 1.5}


def test_blank_values_become_none():
    product = parse_product(
        '{"name": "М", "manufacturer": " ", "description": "", '
        '"specs": {"питание": "  ", "масса": "-", "материал": "Н/Д", "резьба": "нет данных"}}'
    )
    assert product.manufacturer is None
    assert product.description is None
    assert set(product.specs.values()) == {None}


def test_null_specs_mean_no_specs():
    assert parse_product('{"name": "М", "specs": null}').specs == {}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"name": "Манометр",}', "Некорректный JSON: строка 1"),
        ("[1, 2]", "Ожидается JSON-объект"),
        ('{"specs": {}}', "Поле name обязательно и не может быть пустым"),
        ('{"name": "   "}', "Поле name обязательно и не может быть пустым"),
        ('{"name": "М", "specs": {"диапазон": {"от": 0}}}', "Значение specs.диапазон должно быть строкой или числом"),
        ('{"name": "М", "specs": {"подсветка": true}}', "Значение specs.подсветка должно быть строкой или числом"),
        ('{"name": "М", "specs": {"масса": NaN}}', "Некорректный JSON"),
        ('{"name": "М", "description": 5}', "Поле description: неверный тип данных"),
        ('{"name": "М", "characteristics": {}}', "Неизвестное поле characteristics"),
        (b'{"name": "\xff"}', "Файл не в кодировке UTF-8"),
        ("[" * 200000, "Некорректный JSON"),
        ('{"name": "М", "specs": {"a": ' + "1" * 5000 + "}}", "Некорректный JSON"),
    ],
)
def test_reports_bad_input_once(text, expected):
    with pytest.raises(InputError) as exc_info:
        parse_product(text)
    assert len(exc_info.value.errors) == 1
    assert expected in exc_info.value.errors[0]
