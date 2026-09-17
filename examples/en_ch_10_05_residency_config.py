from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

JURISDICTION = {"eu-north": "eu", "eu-west": "eu", "us-east": "us", "global": "multi"}


class DataClass(IntEnum):
    PUBLIC = 0          # published benefit rules
    PERSONAL = 1        # citizens' applications and cases
    SPECIAL = 2         # special categories: health, disability


class Placement(IntEnum):
    REGIONAL_ENDPOINT = 0
    PERIMETER = 1
    SOVEREIGN_CLOUD = 2
    CUSTOMER_GPUS = 3


class Keys(StrEnum):
    PROVIDER = "provider_managed"
    CUSTOMER = "customer_managed"       # key in the customer's KMS: revoking it makes data unreadable
    EXTERNAL = "external_manager"       # key outside the provider's cloud


class Endpoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    region: str
    self_hosted: bool = False
    retains_prompts: bool = False       # request logs or caches on the provider's side


def required_placement(data: DataClass, exclusive_control: bool, offline: bool) -> Placement:
    """The decision tree of the diagram: data class, control, link to the provider."""
    if data is DataClass.PUBLIC:
        return Placement.REGIONAL_ENDPOINT
    if not exclusive_control:
        return Placement.PERIMETER
    return Placement.CUSTOMER_GPUS if offline else Placement.SOVEREIGN_CLOUD


class Deployment(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    data: DataClass
    jurisdiction: str
    exclusive_control: bool             # keys and operations with the customer only
    offline: bool
    placement: Placement
    storage_region: str
    keys: Keys
    perimeter: bool
    endpoint: Endpoint

    def problems(self) -> list[str]:
        out: list[str] = []
        need = required_placement(self.data, self.exclusive_control, self.offline)
        if self.placement < need:
            out.append(f"placement {self.placement.name} is weaker than the required {need.name}")
        for what, region in (("storage", self.storage_region), ("endpoint", self.endpoint.region)):
            if JURISDICTION.get(region) != self.jurisdiction:
                out.append(f"{what} in region {region} is outside jurisdiction {self.jurisdiction}")
        if self.data >= DataClass.PERSONAL:
            if self.keys is Keys.PROVIDER:
                out.append("personal data requires customer-managed keys")
            if not self.perimeter:
                out.append("personal data requires a service perimeter")
            if self.endpoint.retains_prompts:
                out.append("the endpoint retains prompts: a zero-retention mode is needed")
        if self.placement >= Placement.SOVEREIGN_CLOUD and self.keys is not Keys.EXTERNAL:
            out.append("sovereign placement requires keys outside the provider's cloud")
        if self.placement is Placement.CUSTOMER_GPUS and not self.endpoint.self_hosted:
            out.append("without a provider link the model runs on site")
        return out

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if problems := self.problems():
            raise ValueError("; ".join(problems))
        return self


def variant(base: Deployment, **changes: object) -> Deployment:
    """model_copy does not validate; a variant is rebuilt through validation."""
    return Deployment.model_validate(base.model_dump() | changes)


if __name__ == "__main__":
    cases = Deployment(name="citizen-cases", data=DataClass.PERSONAL, jurisdiction="eu",
                       exclusive_control=False, offline=False, placement=Placement.PERIMETER,
                       storage_region="eu-north", keys=Keys.CUSTOMER, perimeter=True,
                       endpoint=Endpoint(region="eu-west"))
    rules = variant(cases, name="benefit-rules", data=DataClass.PUBLIC,
                    placement=Placement.REGIONAL_ENDPOINT, keys=Keys.PROVIDER, perimeter=False)
    assert cases.problems() == [] and rules.problems() == []
    try:
        variant(cases, keys=Keys.PROVIDER, endpoint=Endpoint(region="global", retains_prompts=True))
    except ValidationError as err:
        text = str(err)
        assert "global" in text and "customer-managed keys" in text and "zero-retention" in text
    else:
        raise AssertionError("a global endpoint for citizens' cases must be rejected")
    try:
        variant(cases, data=DataClass.SPECIAL, exclusive_control=True)
    except ValidationError as err:
        assert "SOVEREIGN_CLOUD" in str(err) and "outside the provider" not in str(err)
    else:
        raise AssertionError("special categories under exclusive control require a sovereign cloud")
    print("two configurations accepted, two rejected with reasons")
