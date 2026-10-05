"""Pydantic schema for the curtain SDN network inventory.

Addresses intentionally remain normalized hexadecimal strings so JSON and YAML
serialization cannot silently turn them into decimal values.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


def _normalize_hex_address(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("address must be a quoted hexadecimal string")
    candidate = value.strip().lower()
    if not candidate.startswith("0x"):
        raise ValueError("address must start with 0x")
    try:
        numeric = int(candidate[2:], 16)
    except ValueError as exc:
        raise ValueError("address must contain hexadecimal digits") from exc
    if not 1 <= numeric <= 0xFFFFFF:
        raise ValueError("address must be in the range 0x1..0xffffff")
    return f"0x{numeric:x}"


HexAddress = Annotated[
    str,
    BeforeValidator(_normalize_hex_address),
    StringConstraints(pattern=r"^0x[0-9a-f]{1,6}$"),
]
NonEmptyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class St30Rs485Configuration(StrictModel):
    """Per-motor configuration for the ST30 RS-485 devices in the image."""

    protocol: Literal["ST30_RS485"] = "ST30_RS485"
    orientation_degrees: int = Field(ge=0, le=359)
    down_limit_counts: int = Field(
        ge=0,
        le=0xFFFF,
        description="Raw pulse/count position of the down limit; 0 means not calibrated.",
    )


class Curtain(StrictModel):
    address: HexAddress
    name: NonEmptyName
    description: NonEmptyName
    installed: date
    configuration: St30Rs485Configuration


class SdnSwitch(StrictModel):
    address: HexAddress
    name: NonEmptyName
    description: NonEmptyName
    model: Literal["SDN_SWITCH"] = "SDN_SWITCH"
    installed: date


class CurtainGroup(StrictModel):
    address: HexAddress
    name: NonEmptyName
    description: NonEmptyName
    curtains: list[NonEmptyName] = Field(min_length=1)


class InventoryMetadata(StrictModel):
    source: NonEmptyName
    source_date_format: Literal["MM/DD/YYYY"]
    zero_down_limit_counts_mean: Literal["not_calibrated"]


class CurtainNetworkConfig(StrictModel):
    schema_version: Literal[1]
    metadata: InventoryMetadata
    curtains: list[Curtain]
    switches: list[SdnSwitch]
    groups: list[CurtainGroup]

    @model_validator(mode="after")
    def validate_inventory(self) -> "CurtainNetworkConfig":
        device_names = [item.name for item in [*self.curtains, *self.switches]]
        device_addresses = [item.address for item in [*self.curtains, *self.switches]]
        curtain_names = {item.name for item in self.curtains}
        group_names = [item.name for item in self.groups]
        group_addresses = [item.address for item in self.groups]

        if len(device_names) != len(set(device_names)):
            raise ValueError("curtain and switch names must be unique")
        if len(device_addresses) != len(set(device_addresses)):
            raise ValueError("curtain and switch addresses must be unique")
        if len(group_names) != len(set(group_names)):
            raise ValueError("group names must be unique")
        if len(group_addresses) != len(set(group_addresses)):
            raise ValueError("group addresses must be unique")

        for group in self.groups:
            if len(group.curtains) != len(set(group.curtains)):
                raise ValueError(f"group {group.name!r} contains duplicate curtains")
            unknown = sorted(set(group.curtains) - curtain_names)
            if unknown:
                raise ValueError(
                    f"group {group.name!r} references unknown curtains: {unknown}"
                )
        return self

