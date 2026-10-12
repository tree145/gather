"""Contracts for the standalone, explicitly deterministic consumer demo."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


Dimension = Annotated[float, Field(gt=0, le=500)]
Dimensions = tuple[Dimension, Dimension, Dimension]
Constraint = Literal["price_ntd", "weight_g", "laptop_inches", "capacity_l", "dimensions_cm"]


class CompressionEvidence(BaseModel):
    source_label: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=3, max_length=1500)
    conditions: str = Field(min_length=3, max_length=500)
    compressed_dimensions_cm: Dimensions
    stance: Literal["supporting", "conflicting"] = "supporting"


class ProductInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    brand: str = Field(default="自訂商品", max_length=80)
    description: str = Field(min_length=10, max_length=20000)
    compression_evidence: list[CompressionEvidence] = Field(default_factory=list, max_length=5)


class RequirementText(BaseModel):
    text: str = Field(min_length=3, max_length=2000)

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Please describe your needs in at least three characters.")
        return value.strip()


class Requirements(RequirementText):
    budget_ntd: float | None = Field(default=None, ge=0, le=1000000)
    max_weight_g: float | None = Field(default=None, gt=0, le=50000)
    laptop_inches: float | None = Field(default=None, gt=0, le=30)
    min_capacity_l: float | None = Field(default=None, gt=0, le=200)
    priority: Literal["balanced", "comfort", "lightweight", "value"] = "balanced"
    max_dimensions_cm: Dimensions | None = None
    decision_mode: Literal["tradeoff", "strict"] = "tradeoff"
    hard_constraints: list[Constraint] = Field(default_factory=list, max_length=5)
    accept_review_conditions: bool = False
    wants_bottle_pocket: bool = False


class RecommendRequest(BaseModel):
    product_ids: list[str] = Field(min_length=1, max_length=6)
    requirements: Requirements
