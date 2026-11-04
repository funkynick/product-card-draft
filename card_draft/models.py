from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, field_validator

NO_DATA = "данных нет"

# Пометки, которыми в каталогах часто заполняют пустую характеристику.
BLANK_VALUES = {"", "-", "—", "–", "н/д", "нет", "нет данных", "данных нет"}

# Строгие типы: иначе pydantic превращает JSON-значение true в 1.
SpecValue = StrictStr | StrictInt | StrictFloat | None


class ProductInput(BaseModel):
    # Опечатка в имени поля не должна выглядеть как нехватка данных.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1)
    manufacturer: str | None = None
    specs: dict[str, SpecValue] = Field(default_factory=dict)
    description: str | None = None

    @field_validator("manufacturer", "description")
    @classmethod
    def _blank_text_to_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("specs", mode="before")
    @classmethod
    def _null_specs_to_empty(cls, specs: object) -> object:
        return {} if specs is None else specs

    @field_validator("specs")
    @classmethod
    def _blank_specs_to_none(cls, specs: dict[str, SpecValue]) -> dict[str, SpecValue]:
        return {
            name: None if isinstance(value, str) and value.lower() in BLANK_VALUES else value
            for name, value in specs.items()
        }


class LlmDraft(BaseModel):
    """Ответ модели. Значений характеристик здесь нет: их подставляет код."""

    model_config = ConfigDict(extra="forbid")

    seo_title: str
    seo_description: str
    search_queries: list[str]
    suits_for: str
    solves: str
    needs_clarification: list[str]


class Characteristic(BaseModel):
    name: str
    value: str


class CardResult(LlmDraft):
    status: Literal["ready", "needs_review", "insufficient_data"]
    name: str
    manufacturer: str | None
    characteristics: list[Characteristic]
    missing_fields: list[str]
    problems: list[str]
