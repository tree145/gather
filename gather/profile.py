"""Shopper profiles adapted from the 0815 project."""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


SearchValue = Union[
    str,
    int,
    float,
    bool,
    None,
    list[Union[str, int, float, bool, None]],
    dict[str, Union[str, int, float, bool, None]],
]


class SearchLocation(BaseModel):
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None


class SearchBudget(BaseModel):
    min_amount: Optional[float] = Field(default=None, ge=0)
    max_amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    flexibility: Literal["hard", "soft"] = "soft"

    @model_validator(mode="after")
    def validate_range(self) -> "SearchBudget":
        if (
            self.min_amount is not None
            and self.max_amount is not None
            and self.min_amount > self.max_amount
        ):
            raise ValueError("budget min_amount cannot exceed max_amount")
        return self


class SearchCriterion(BaseModel):
    attribute: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    operator: Literal[
        "eq",
        "neq",
        "lte",
        "gte",
        "between",
        "in",
        "not_in",
        "contains",
        "not_contains",
        "supports",
        "exists",
        "maximize",
        "minimize",
    ]
    value: SearchValue = None
    unit: Optional[str] = None
    importance: Literal["must", "should", "nice_to_have"] = "should"
    reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_value(self) -> "SearchCriterion":
        value_optional = {"exists", "maximize", "minimize"}
        if self.operator not in value_optional and self.value is None:
            raise ValueError(f"criterion operator '{self.operator}' requires a value")
        if self.operator == "between":
            if not isinstance(self.value, dict) or not {"min", "max"} <= self.value.keys():
                raise ValueError("between criterion requires value.min and value.max")
            minimum = self.value["min"]
            maximum = self.value["max"]
            if (
                isinstance(minimum, (int, float))
                and not isinstance(minimum, bool)
                and isinstance(maximum, (int, float))
                and not isinstance(maximum, bool)
                and minimum > maximum
            ):
                raise ValueError("between criterion value.min cannot exceed value.max")
        return self


class ReferenceProduct(BaseModel):
    name: str = Field(min_length=1)
    relation: Literal[
        "owns",
        "likes",
        "dislikes",
        "compare_with",
        "alternative_to",
        "compatible_with",
    ] = "compare_with"
    notes: Optional[str] = None


class PersonaProfile(BaseModel):
    persona_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    label: str = Field(min_length=1)
    relationship_to_buyer: str = "self"
    age: Optional[int] = Field(default=None, ge=0, le=120)
    occupation: Optional[str] = None
    location: Optional[SearchLocation] = None
    budget: Optional[SearchBudget] = None
    use_cases: list[str] = Field(default_factory=list)
    criteria: list[SearchCriterion] = Field(default_factory=list)
    reference_products: list[ReferenceProduct] = Field(default_factory=list)
    context: dict[str, SearchValue] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
