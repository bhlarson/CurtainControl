"""Validated JSON configuration, credentials, and the only local-file boundary for settings."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from croniter import croniter
from pydantic import (BaseModel, BeforeValidator, ConfigDict, Field, SecretStr, ValidationError,
                      WithJsonSchema, field_validator, model_validator)

MAX_ADDRESS = 0xFFFFFF
KNOWN_TIMING_PROFILES = frozenset({"st30-default"})
ALLOWED_ICONS = frozenset({
    "fa-home", "fa-door-open", "fa-sun", "fa-mobile-alt", "fa-bed", "fa-couch", "fa-utensils",
    "fa-bath", "fa-briefcase", "fa-stairs", "fa-window-maximize",
})
UNIT_KIND = {
    "degC": "temperature", "degF": "temperature", "K": "temperature",
    "m_per_s": "speed", "km_per_h": "speed", "mph": "speed",
    "percent": "percent", "mm_per_h": "rate", "deg": "angle", "code": "code", "boolean": "boolean",
}
BUILTIN_FIELDS: dict[str, dict[str, str]] = {
    "weather": {
        "outside_temperature": "degC", "cloud_cover": "percent", "precipitation_rate": "mm_per_h",
        "precipitation_probability": "percent", "wind_speed": "m_per_s", "wind_gust": "m_per_s",
        "condition_code": "code", "alert_active": "boolean",
    },
    "celestial": {
        "moon_visible": "boolean", "moon_altitude": "deg", "moon_illumination": "percent",
        "sun_altitude": "deg",
    },
}
SOLAR_EVENTS = (
    "sunrise", "sunset", "civil_dawn", "civil_dusk", "nautical_dawn", "nautical_dusk",
    "astronomical_dawn", "astronomical_dusk",
)
LUNAR_EVENTS = ("moonrise", "moonset")


class ConfigError(Exception):
    """Safe-to-display configuration/credential failure (never contains input values)."""


def _parse_address(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("address must not be a boolean")
    if isinstance(value, str):
        text = value.strip()
        try:
            value = int(text, 16) if text.lower().startswith("0x") else int(text, 10)
        except ValueError:
            raise ValueError("address must be a decimal or 0x-prefixed hexadecimal integer") from None
    if not isinstance(value, int):
        raise ValueError("address must be an integer")
    if not 1 <= value <= MAX_ADDRESS:
        raise ValueError("address must be in 1..0xFFFFFF")
    return value


_ADDRESS_INPUT_SCHEMA = {
    "anyOf": [
        {"type": "integer", "minimum": 1, "maximum": MAX_ADDRESS},
        {"type": "string", "pattern": "^(0[xX][0-9A-Fa-f]{1,6}|[0-9]{1,8})$"},
    ]
}
Address = Annotated[int, BeforeValidator(_parse_address),
                    WithJsonSchema(_ADDRESS_INPUT_SCHEMA, mode="validation")]
Percent = Annotated[int, Field(strict=True, ge=0, le=100)]


def parse_address(value: Any) -> int:
    return _parse_address(value)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- SDN backend
class SerialConfig(StrictModel):
    port: str = "/dev/ttyUSB0"
    baudrate: int = Field(4800, gt=0)
    bytesize: Literal[7, 8] = 8
    parity: Literal["odd", "even", "none"] = "odd"
    stopbits: Literal[1, 2] = 1


class RecordingConfig(StrictModel):
    enabled: bool = False
    directory: str = "traces"


class SimDeviceConfig(StrictModel):
    motor: str
    initial_position_percent: Percent = 0
    travel_time_seconds: float = Field(20.0, gt=0)


class SimScenario(StrictModel):
    kind: Literal["silence", "late_reply", "bad_checksum", "fragment", "coalesce", "offline",
                  "blocked", "disconnect"]
    motor: Optional[str] = None
    delay_seconds: float = Field(0.5, ge=0)
    after_requests: Optional[int] = Field(None, ge=0)
    blocked_at_percent: Optional[Percent] = None
    count: Optional[int] = Field(None, ge=1)

    @model_validator(mode="after")
    def _check(self) -> "SimScenario":
        if self.kind == "blocked" and self.blocked_at_percent is None:
            raise ValueError("blocked scenario requires blocked_at_percent")
        if self.kind == "disconnect" and self.after_requests is None:
            raise ValueError("disconnect scenario requires after_requests")
        if self.kind not in ("disconnect",) and self.motor is None:
            raise ValueError("scenario requires a motor")
        return self


class SimulationConfig(StrictModel):
    seed: int = 0
    time_scale: float = Field(1.0, gt=0)
    timing_profile: str = "st30-default"
    devices: tuple[SimDeviceConfig, ...] = ()
    scenarios: tuple[SimScenario, ...] = ()

    @field_validator("timing_profile")
    @classmethod
    def _profile(cls, value: str) -> str:
        if value not in KNOWN_TIMING_PROFILES:
            raise ValueError("unknown timing profile")
        return value


class SdnConfig(StrictModel):
    mode: Literal["real", "simulated"]
    controller_address: Address = 1
    recording: RecordingConfig = RecordingConfig()
    simulation: Optional[SimulationConfig] = None
    bus_min_interval_seconds: float = Field(0.1, ge=0.025)
    receive_buffer_bytes: int = Field(4096, ge=64)
    incomplete_frame_expiry_seconds: float = Field(1.0, gt=0)

    @model_validator(mode="after")
    def _check(self) -> "SdnConfig":
        if self.mode == "simulated" and self.simulation is None:
            raise ValueError("simulated mode requires a simulation section")
        return self


# ---------------------------------------------------------------- monitoring/control
class MonitoringConfig(StrictModel):
    poll_active_interval_seconds: float = Field(0.5, gt=0)
    poll_idle_interval_seconds: float = Field(60.0, gt=0)
    query_timeout_seconds: float = Field(0.5, gt=0)
    position_freshness_seconds: float = Field(90.0, gt=0)
    status_freshness_seconds: float = Field(90.0, gt=0)
    offline_failure_threshold: int = Field(3, ge=1)
    verification_max_skew_seconds: float = Field(2.0, gt=0)
    travel_deadline_seconds: float = Field(60.0, gt=0)
    tolerance_percent: int = Field(3, ge=0, le=100)
    retry_enabled: bool = False
    retry_cooldown_seconds: float = Field(5.0, ge=0)
    history_limit: int = Field(100, ge=1)
    event_queue_size: int = Field(64, ge=1)
    reconnect_interval_seconds: float = Field(5.0, gt=0)

    @model_validator(mode="after")
    def _check(self) -> "MonitoringConfig":
        limit = min(self.position_freshness_seconds, self.status_freshness_seconds)
        if self.verification_max_skew_seconds > limit:
            raise ValueError("verification_max_skew_seconds must not exceed the freshness limits")
        if limit < self.poll_idle_interval_seconds:
            raise ValueError("freshness limits must cover the idle polling interval")
        if self.poll_active_interval_seconds > self.poll_idle_interval_seconds:
            raise ValueError("active polling interval must not exceed the idle interval")
        return self


class ControlConfig(StrictModel):
    state_file: str = "control-state.json"
    startup_target_policy: Literal["fresh_actual_if_missing", "configured_default", "none"] = \
        "fresh_actual_if_missing"
    on_corrupt_state: Literal["fail", "read_only"] = "fail"
    position_tolerance_percent: int = Field(2, ge=0, le=100)
    local_input_debounce_seconds: float = Field(1.0, ge=0)
    reconcile_interval_seconds: float = Field(30.0, gt=0)
    retry_limit: int = Field(1, ge=0)
    retry_cooldown_seconds: float = Field(10.0, ge=0)
    reconciliation_deadline_seconds: float = Field(120.0, gt=0)
    handled_event_history_limit: int = Field(1000, ge=1)
    coherence_seconds: float = Field(1.0, gt=0)
    disabled_sources: tuple[Literal["web", "alexa", "somfy_button", "schedule", "environment"], ...] = ()


class LocationConfig(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str
    elevation_m: float = 0.0

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return _validate_timezone(value)


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError("unknown IANA timezone") from None
    return value


class QuickRoom(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    label: str = Field(min_length=1, max_length=40)
    target: str = Field(min_length=1)
    icon: str

    @field_validator("icon")
    @classmethod
    def _icon(cls, value: str) -> str:
        if value not in ALLOWED_ICONS:
            raise ValueError("icon is not in the local sprite allowlist")
        return value


DEFAULT_QUICK_ROOMS = (
    QuickRoom(id="all", label="Full Home", target="All Windows", icon="fa-home"),
    QuickRoom(id="entry", label="Entry", target="Entry", icon="fa-door-open"),
    QuickRoom(id="sunroom", label="Sunroom", target="Sunroom", icon="fa-sun"),
    QuickRoom(id="studio", label="Studio", target="Studio", icon="fa-mobile-alt"),
)


class WebConfig(StrictModel):
    quick_rooms: tuple[QuickRoom, ...] = DEFAULT_QUICK_ROOMS
    auth_mode: Literal["trusted_network", "bearer"] = "trusted_network"


class WeatherConfig(StrictModel):
    enabled: bool = False
    provider: Literal["generic", "nws"] = "generic"
    user_agent: str = Field("CurtainControl/1.0", min_length=1)
    request_timeout_seconds: float = Field(10.0, gt=0, le=60)
    discovery_refresh_seconds: int = Field(86400, gt=0)
    url: Optional[str] = None
    poll_interval_seconds: int = Field(300, gt=0)
    max_age_seconds: int = Field(900, gt=0)
    field_map: dict[str, str] = {}
    units: dict[str, str] = {}
    api_key_header: Optional[str] = "X-API-Key"

    @model_validator(mode="after")
    def _check(self) -> "WeatherConfig":
        if self.enabled and self.provider == "generic" and not (self.url and self.field_map):
            raise ValueError("enabled generic weather requires url and field_map; set provider to 'nws' for key-free weather using location")
        if self.provider == "nws" and (self.url or self.field_map or self.units):
            raise ValueError("NWS uses configured location and built-in observation mappings")
        if not self.user_agent.strip() or any(ord(char) < 32 or ord(char) > 126 for char in self.user_agent):
            raise ValueError("weather user_agent must contain printable ASCII")
        for name in self.field_map:
            if name not in BUILTIN_FIELDS["weather"]:
                raise ValueError("unknown weather field")
        for name, unit in self.units.items():
            if name not in BUILTIN_FIELDS["weather"] or unit not in UNIT_KIND:
                raise ValueError("invalid weather unit mapping")
            if UNIT_KIND[unit] != UNIT_KIND[BUILTIN_FIELDS["weather"][name]]:
                raise ValueError("weather unit is incompatible with its field")
        return self


class DataSourcesConfig(StrictModel):
    weather: WeatherConfig = WeatherConfig()
    moon_horizon_altitude_degrees: float = 0.0


# ---------------------------------------------------------------- inventory
class MotorConfig(StrictModel):
    address: Address
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    type: str = "ST30 RS485"
    install: str = ""
    angle: float = 0
    distance: float = 0
    invert_position: bool = False
    enabled: bool = True
    startup_percent: Optional[Percent] = None


class GroupConfig(StrictModel):
    address: Address
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    devices: tuple[str, ...] = Field(min_length=1)
    enabled: bool = True


# ---------------------------------------------------------------- schedules
Operator = Literal["<", "<=", ">", ">=", "==", "!="]
MAX_CONDITION_DEPTH = 4
MAX_CONDITION_NODES = 16


class ConditionNode(StrictModel):
    all: Optional[tuple["ConditionNode", ...]] = None
    any: Optional[tuple["ConditionNode", ...]] = None
    not_: Optional["ConditionNode"] = Field(None, alias="not")
    source: Optional[str] = Field(None, pattern=r"^[a-z][a-z0-9_]{0,31}$")
    field: Optional[str] = Field(None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    operator: Optional[Operator] = None
    value: Optional[float | bool | str] = None
    unit: Optional[str] = None
    max_age_seconds: Optional[int] = Field(None, gt=0)
    hysteresis: float = Field(0.0, ge=0)
    missing_data: Literal["skip", "false"] = "skip"

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def _check(self) -> "ConditionNode":
        kinds = [self.all is not None, self.any is not None, self.not_ is not None,
                 self.source is not None]
        if sum(kinds) != 1:
            raise ValueError("a condition node must be exactly one of all, any, not, or a leaf")
        if self.all is not None or self.any is not None:
            if not (self.all or self.any):
                raise ValueError("all/any must contain at least one condition")
        if self.source is not None:
            if self.field is None or self.operator is None or self.value is None:
                raise ValueError("leaf requires field, operator, and value")
            if self.max_age_seconds is None:
                raise ValueError("leaf requires max_age_seconds")
            if isinstance(self.value, (bool, str)) and self.operator not in ("==", "!="):
                raise ValueError("boolean/string values support only == and !=")
            if isinstance(self.value, float) and not isinstance(self.value, bool):
                if self.unit is None:
                    raise ValueError("numeric condition requires a unit")
            if self.unit is not None and self.unit not in UNIT_KIND:
                raise ValueError("unsupported unit")
            builtin = BUILTIN_FIELDS.get(self.source)
            if builtin is not None:
                if self.field not in builtin:
                    raise ValueError("unsupported field for source")
                if self.unit is not None and UNIT_KIND[self.unit] != UNIT_KIND[builtin[self.field]]:
                    raise ValueError("unit is incompatible with the field")
        elif self.field or self.operator or self.value is not None or self.unit:
            raise ValueError("leaf fields are not allowed on all/any/not nodes")
        return self

    def depth_and_count(self) -> tuple[int, int]:
        children: list[ConditionNode] = list(self.all or ()) + list(self.any or ())
        if self.not_ is not None:
            children.append(self.not_)
        if not children:
            return 1, 1
        results = [child.depth_and_count() for child in children]
        return 1 + max(d for d, _ in results), 1 + sum(c for _, c in results)


ConditionNode.model_rebuild()


class ActionSpec(StrictModel):
    action: Literal["open", "close", "set_percent"]
    percentage: Optional[Percent] = None
    target_type: Literal["motor", "group"]
    target: str = Field(min_length=1)
    source: Literal["scheduler", "environment"] = "scheduler"

    @model_validator(mode="after")
    def _check(self) -> "ActionSpec":
        if (self.action == "set_percent") != (self.percentage is not None):
            raise ValueError("percentage is required for, and only allowed with, set_percent")
        return self


_CRON_FIELD = re.compile(r"^[0-9*/,\-]+$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleRule(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    enabled: bool = True
    timer: Literal["cron", "time", "once", "solar", "lunar", "environment"]
    expression: Optional[str] = None
    time: Optional[str] = None
    days: Optional[tuple[int, ...]] = None
    at: Optional[datetime] = None
    timestamp_ms: Optional[int] = Field(None, ge=0)
    event: Optional[str] = None
    offset_seconds: int = Field(0, ge=-86400, le=86400)
    timezone: Optional[str] = None
    action: ActionSpec
    conditions: Optional[ConditionNode] = None
    debounce_seconds: int = Field(0, ge=0)
    cooldown_seconds: int = Field(0, ge=0)
    priority: int = 0
    missed_event: Literal["skip", "run_within_grace"] = "skip"
    run_within_grace_seconds: int = Field(0, ge=0)
    dst_nonexistent: Literal["skip", "shift_forward"] = "skip"
    dst_ambiguous: Literal["first", "second"] = "first"
    evaluate_interval_seconds: int = Field(60, gt=0)
    startup_policy: Literal["baseline_only", "run_within_grace"] = "baseline_only"

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _validate_timezone(value)

    @model_validator(mode="after")
    def _check(self) -> "ScheduleRule":
        timer = self.timer
        if timer == "cron":
            fields = (self.expression or "").split()
            if len(fields) != 5 or not all(_CRON_FIELD.match(f) for f in fields) \
                    or not croniter.is_valid(self.expression):
                raise ValueError("expression must be a standard five-field numeric cron expression")
        elif timer == "time":
            if not self.time or not _TIME.match(self.time):
                raise ValueError("time must be HH:MM")
            if self.days is not None and not all(0 <= d <= 6 for d in self.days):
                raise ValueError("days must be 0..6 with 0=Sunday")
        elif timer == "once":
            if (self.at is None) == (self.timestamp_ms is None):
                raise ValueError("once requires exactly one of at or timestamp_ms")
            if self.at is not None and self.at.tzinfo is None:
                raise ValueError("at must be timezone-aware")
        elif timer == "solar":
            if self.event not in SOLAR_EVENTS:
                raise ValueError("unknown solar event")
        elif timer == "lunar":
            if self.event not in LUNAR_EVENTS:
                raise ValueError("unknown lunar event")
        elif timer == "environment":
            if self.conditions is None:
                raise ValueError("environment rules require conditions")
        if self.missed_event == "run_within_grace" and self.run_within_grace_seconds <= 0:
            raise ValueError("run_within_grace requires a positive run_within_grace_seconds")
        if self.conditions is not None:
            depth, count = self.conditions.depth_and_count()
            if depth > MAX_CONDITION_DEPTH or count > MAX_CONDITION_NODES:
                raise ValueError("condition tree exceeds the depth or size limit")
        expected_source = "environment" if timer == "environment" else "scheduler"
        if self.action.source != expected_source and timer == "environment":
            raise ValueError("environment rules must use source environment")
        return self


# ---------------------------------------------------------------- system config
class SystemConfig(StrictModel):
    schema_version: Literal[1]
    sdn: SdnConfig
    serial: Optional[SerialConfig] = None
    monitoring: MonitoringConfig = MonitoringConfig()
    control: ControlConfig = ControlConfig()
    location: LocationConfig
    web: WebConfig = WebConfig()
    data_sources: DataSourcesConfig = DataSourcesConfig()
    motors: tuple[MotorConfig, ...] = ()
    groups: tuple[GroupConfig, ...] = ()
    schedules: tuple[ScheduleRule, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> "SystemConfig":
        motor_names = [m.name for m in self.motors]
        group_names = [g.name for g in self.groups]
        if len(set(motor_names)) != len(motor_names):
            raise ValueError("duplicate motor name")
        if len(set(group_names)) != len(group_names):
            raise ValueError("duplicate group name")
        addresses = [m.address for m in self.motors] + [g.address for g in self.groups]
        if len(set(addresses)) != len(addresses):
            raise ValueError("duplicate motor/group address")
        if self.sdn.controller_address in addresses:
            raise ValueError("controller address collides with a motor or group address")
        for group in self.groups:
            if len(set(group.devices)) != len(group.devices):
                raise ValueError("duplicate group member")
            for member in group.devices:
                if member not in motor_names:
                    raise ValueError("group member does not refer to a configured motor")
        ids = [r.id for r in self.schedules]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate schedule id")
        for rule in self.schedules:
            names = motor_names if rule.action.target_type == "motor" else group_names
            if rule.action.target not in names:
                raise ValueError("schedule target is not configured")
        if self.sdn.mode == "real" and self.serial is None:
            raise ValueError("real mode requires a serial section")
        sim = self.sdn.simulation
        if sim is not None and self.sdn.mode == "simulated":
            device_names = [d.motor for d in sim.devices]
            if len(set(device_names)) != len(device_names):
                raise ValueError("duplicate simulated device")
            if set(device_names) != set(motor_names):
                raise ValueError("simulation devices must match configured motors exactly")
        if sim is not None:
            for scenario in sim.scenarios:
                if scenario.motor is not None and scenario.motor not in motor_names:
                    raise ValueError("scenario targets an unknown motor")
        return self


def config_fingerprint(config: SystemConfig) -> str:
    text = json.dumps(config.model_dump(mode="json", by_alias=True), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Inventory:
    """Read-only name/address index over a validated configuration."""

    def __init__(self, config: SystemConfig) -> None:
        self.config = config
        self.motors = {m.name: m for m in config.motors}
        self.groups = {g.name: g for g in config.groups}
        self._by_address = {m.address: m for m in config.motors}

    def motor_by_address(self, address: int) -> Optional[MotorConfig]:
        return self._by_address.get(address)

    def group_members(self, group_id: str) -> tuple[str, ...]:
        return self.groups[group_id].devices

    def expand(self, target_type: str, target: str) -> tuple[str, ...]:
        if target_type == "motor":
            if target not in self.motors:
                raise KeyError(target)
            return (target,)
        if target_type == "group":
            if target not in self.groups:
                raise KeyError(target)
            return self.groups[target].devices
        raise KeyError(target_type)


# ---------------------------------------------------------------- credentials
class WeatherCredentials(StrictModel):
    api_key: SecretStr


class AuthCredentials(StrictModel):
    control_token: Optional[SecretStr] = None
    admin_token: Optional[SecretStr] = None


class Credentials(StrictModel):
    weather: Optional[WeatherCredentials] = None
    auth: Optional[AuthCredentials] = None


def _safe_errors(error: ValidationError) -> str:
    parts = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        location = ".".join(str(p) for p in item["loc"]) or "<root>"
        parts.append(f"{location}: {item['msg']}")
    return "; ".join(parts)


def validate_config(data: Any) -> SystemConfig:
    try:
        return SystemConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigError(f"invalid configuration: {_safe_errors(error)}") from None


def load_config(path: str | os.PathLike[str]) -> SystemConfig:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"cannot read configuration: {error.strerror}") from None
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ConfigError(f"configuration is not valid JSON: {error}") from None
    config = validate_config(data)
    check_destinations(config, Path(path).resolve().parent)
    return config


def resolve_path(base_dir: str | os.PathLike[str], value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path(base_dir) / path


def check_destinations(config: SystemConfig, base_dir: str | os.PathLike[str]) -> None:
    """Fail early when an enabled recording/state destination cannot be written."""
    targets: list[tuple[str, Path]] = [("control state", resolve_path(base_dir, config.control.state_file).parent)]
    if config.sdn.recording.enabled:
        targets.append(("recording", resolve_path(base_dir, config.sdn.recording.directory)))
    for label, directory in targets:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory):
                pass
        except OSError:
            raise ConfigError(f"{label} destination is not writable") from None


def atomic_write_text(path: str | os.PathLike[str], text: str) -> None:
    """Write via a same-directory temp file and atomic replace; the old file survives any failure."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def write_config_atomic(path: str | os.PathLike[str], config: SystemConfig | dict[str, Any]) -> SystemConfig:
    """Validate the whole replacement, then atomically replace the file."""
    validated = config if isinstance(config, SystemConfig) else validate_config(config)
    text = json.dumps(validated.model_dump(mode="json", by_alias=True, exclude_none=True), indent=2)
    try:
        atomic_write_text(path, text + "\n")
    except OSError as error:
        raise ConfigError(f"cannot write configuration: {error.strerror}") from None
    return validated


def load_credentials(path: str | os.PathLike[str] | None) -> Credentials:
    if path is None:
        return Credentials()
    target = Path(path)
    try:
        status = target.stat()
        if os.name != "nt" and status.st_mode & 0o007:
            raise ConfigError("credential file is readable by other users")
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"cannot read credentials: {error.strerror}") from None
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        raise ConfigError("credential file is not valid YAML") from None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError("credential file must contain a mapping")
    try:
        return Credentials.model_validate(data)
    except ValidationError as error:
        raise ConfigError(f"invalid credentials: {_safe_errors(error)}") from None


def require_credentials(config: SystemConfig, credentials: Credentials) -> None:
    if (config.data_sources.weather.enabled and config.data_sources.weather.provider == "generic"
            and credentials.weather is None):
        raise ConfigError("weather is enabled but weather credentials are missing")
    if config.web.auth_mode == "bearer":
        auth = credentials.auth
        if auth is None or auth.admin_token is None or auth.control_token is None:
            raise ConfigError("bearer authentication requires auth.control_token and auth.admin_token")
