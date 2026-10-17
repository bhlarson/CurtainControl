"""Stateful SDN bus/device simulator, trace recording, and real-versus-simulated fidelity scoring.

The simulator deliberately has its own small encoder/decoder (not the production codec) so that its replies
can be verified against independently generated fixtures.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import (BaseModel, ConfigDict, Field, field_serializer, field_validator,
                      model_validator)

from clock import Clock, SystemClock
from config import (GroupConfig, MotorConfig, SimScenario, SimulationConfig, atomic_write_text,
                    config_fingerprint)
from models import SdnTransportError

TRACE_SCHEMA_VERSION = 1
SOFTWARE_VERSION = "curtaincontrol-0.1"
CMD_STOP, CMD_MOVETO, CMD_GET_POS, CMD_POST_POS, CMD_GET_STATUS, CMD_POST_STATUS = 0x02, 0x03, 0x0C, 0x0D, 0x0E, 0x0F
CAUSE_TARGET_REACHED, CAUSE_EXPLICIT, CAUSE_OBSTACLE = 0x01, 0x02, 0x11
SRC_INTERNAL, SRC_NETWORK, SRC_LOCAL_UI = 0, 1, 2


# ------------------------------------------------------------------ timing profiles
class TimingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    version: str = "1"
    bus_idle_seconds: float = Field(0.025, ge=0)
    response_latency_seconds: float = Field(0.03, ge=0)
    chunk_gap_seconds: float = Field(0.004, ge=0)
    chunk_size: int = Field(0, ge=0)  # 0 = whole frame in one chunk
    jitter_seconds: float = Field(0.0, ge=0)


TIMING_PROFILES = {
    "st30-default": TimingProfile(name="st30-default", jitter_seconds=0.004),
}


# ------------------------------------------------------------------ independent frame helpers
def _encode(src: int, dest: int, cmd: int, data: bytes) -> bytes:
    body = [~cmd & 255, ~(11 + len(data)) & 255, ~0x02 & 255]
    body += [(src >> 16) & 255, (src >> 8) & 255, src & 255]
    body += [~(dest >> shift) & 255 for shift in (0, 8, 16)]
    body += [~b & 255 for b in data]
    total = sum(body) & 0xFFFF
    return bytes(body + [total >> 8, total & 255])


@dataclass(frozen=True)
class _Parsed:
    cmd: int
    src: int
    dest: int
    data: bytes


def _decode(raw: bytes) -> Optional[_Parsed]:
    n = len(raw)
    if n < 11 or n > 32 or (~raw[1] & 0x3F) != n or (~raw[1] & 0x40):
        return None
    if (~raw[2] & 255) not in (0x02, 0x20):
        return None
    if (sum(raw[: n - 2]) & 0xFFFF) != (raw[n - 2] << 8 | raw[n - 1]):
        return None
    dest = sum((~raw[6 + i] & 255) << (8 * i) for i in range(3))
    return _Parsed(~raw[0] & 255, int.from_bytes(raw[3:6], "big"), dest, bytes(~b & 255 for b in raw[9 : n - 2]))


def _scan_stream(stream: bytes) -> list[tuple[int, int, bool, bytes]]:
    """(start, end, valid, raw) frames found in a byte stream (used for scoring only)."""
    out: list[tuple[int, int, bool, bytes]] = []
    pos = 0
    while pos + 3 <= len(stream):
        length_byte = ~stream[pos + 1] & 255
        length = length_byte & 0x3F
        if length_byte & 0x40 or not 11 <= length <= 32 or (~stream[pos + 2] & 255) not in (0x02, 0x20):
            pos += 1
            continue
        if pos + length > len(stream):
            break
        raw = stream[pos : pos + length]
        out.append((pos, pos + length, _decode(raw) is not None, raw))
        pos += length
    return out


# ------------------------------------------------------------------ simulated motor
@dataclass
class _Motor:
    name: str
    address: int
    travel_time: float
    initial: int
    position: float = 0.0
    start_pos: float = 0.0
    started: float = 0.0
    target: float = 0.0
    running: bool = False
    direction: int = 0xFF
    source: int = SRC_INTERNAL
    cause: int = 0
    blocked: bool = False
    blocked_at: Optional[int] = None
    stop_pending_block: bool = False


@dataclass
class _ScenarioState:
    spec: SimScenario
    remaining: Optional[int]


class SdnSim:
    """Raw-byte backend with the same open/close/read/write contract as SerialInterface."""

    def __init__(self, config: SimulationConfig, motors: tuple[MotorConfig, ...],
                 groups: tuple[GroupConfig, ...] = (), clock: Optional[Clock] = None,
                 controller_address: int = 1) -> None:
        if config.timing_profile not in TIMING_PROFILES:
            raise ValueError("unknown timing profile")
        by_name = {m.name: m for m in motors}
        devices = {d.motor: d for d in config.devices}
        if set(devices) != set(by_name):
            raise ValueError("simulation devices must match configured motors")
        self.config = config
        self.profile = TIMING_PROFILES[config.timing_profile]
        self._clock = clock or SystemClock()
        self._controller = controller_address
        self._rng = random.Random(config.seed)
        self._motors = {
            m.name: _Motor(m.name, m.address, devices[m.name].travel_time_seconds,
                           devices[m.name].initial_position_percent)
            for m in motors
        }
        self._by_address = {m.address: m for m in self._motors.values()}
        self._groups = {g.address: tuple(self._motors[n] for n in g.devices) for g in groups}
        self._scenarios = [_ScenarioState(s, s.count) for s in config.scenarios]
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._tasks: set[asyncio.Task[None]] = set()
        self._open = False
        self.generation = 0
        self.requests_received = 0
        self.ignored_requests = 0
        self.bus_idle_violations = 0
        self.writes: list[bytes] = []
        self._last_request_at: Optional[float] = None
        self._disconnected = False

    # ---- backend contract
    async def open(self) -> int:
        self._cancel_tasks()
        self._queue = asyncio.Queue()
        for motor in self._motors.values():
            motor.position = motor.start_pos = float(motor.initial)
            motor.running = False
            motor.direction, motor.source, motor.cause, motor.blocked = 0xFF, SRC_INTERNAL, 0, False
            motor.blocked_at = None
        for state in self._scenarios:
            state.remaining = state.spec.count
        self._rng = random.Random(self.config.seed)
        self.generation += 1
        self.requests_received = self.ignored_requests = self.bus_idle_violations = 0
        self.writes = []
        self._last_request_at = None
        self._disconnected = False
        self._open = True
        return self.generation

    async def close(self) -> None:
        self._open = False
        self._cancel_tasks()
        self._queue = asyncio.Queue()

    async def read(self) -> bytes:
        item = await self._queue.get()
        if isinstance(item, BaseException):
            raise item
        return item

    async def write(self, data: bytes) -> None:
        if not self._open:
            raise SdnTransportError("simulator is closed")
        if self._disconnected:
            raise SdnTransportError("simulated disconnect")
        raw = bytes(data)
        self.writes.append(raw)
        self.requests_received += 1
        for state in self._scenarios:
            if state.spec.kind == "disconnect" and self.requests_received > (state.spec.after_requests or 0):
                self._disconnected = True
                self._queue.put_nowait(SdnTransportError("simulated disconnect"))
                raise SdnTransportError("simulated disconnect")
        now = self._clock.monotonic()
        if self._last_request_at is not None and now - self._last_request_at < self._scaled(self.profile.bus_idle_seconds):
            self.bus_idle_violations += 1
            self.ignored_requests += 1
            self._last_request_at = now
            return
        self._last_request_at = now
        self._handle(raw, now)

    # ---- helpers for tests/scenarios
    def local_button(self, motor_name: str, target_percent: int) -> None:
        """Move a motor as if its Somfy local button were used."""
        motor = self._motors[motor_name]
        self._start_move(motor, float(target_percent), SRC_LOCAL_UI, self._clock.monotonic())

    def position_of(self, motor_name: str) -> float:
        motor = self._motors[motor_name]
        self._settle(motor, self._clock.monotonic())
        return motor.position

    def snapshot(self) -> dict[str, Any]:
        now = self._clock.monotonic()
        out: dict[str, Any] = {}
        for motor in self._motors.values():
            self._settle(motor, now)
            out[motor.name] = {"position": round(motor.position), "motion": "running" if motor.running else "stopped",
                               "fault": "blocked" if motor.blocked else None}
        return out

    # ---- internals
    def _scaled(self, seconds: float) -> float:
        return seconds / self.config.time_scale

    def _cancel_tasks(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()

    def _scenario(self, kind: str, motor: Optional[str]) -> Optional[_ScenarioState]:
        for state in self._scenarios:
            spec = state.spec
            if spec.kind != kind or (spec.motor is not None and spec.motor != motor):
                continue
            if state.remaining is not None and state.remaining <= 0:
                continue
            return state
        return None

    @staticmethod
    def _consume(state: Optional[_ScenarioState]) -> None:
        if state is not None and state.remaining is not None:
            state.remaining -= 1

    def _settle(self, motor: _Motor, now: float) -> None:
        if not motor.running:
            return
        elapsed = (now - motor.started) * self.config.time_scale
        distance = elapsed * (100.0 / motor.travel_time)
        span = abs(motor.target - motor.start_pos)
        if distance >= span:
            motor.position, motor.running = motor.target, False
            if motor.blocked_at is not None and motor.target == float(motor.blocked_at):
                motor.blocked, motor.cause = True, CAUSE_OBSTACLE
            else:
                motor.cause = CAUSE_TARGET_REACHED
        else:
            motor.position = motor.start_pos + (distance if motor.target > motor.start_pos else -distance)

    def _start_move(self, motor: _Motor, target: float, source: int, now: float) -> None:
        self._settle(motor, now)
        scenario = self._scenario("blocked", motor.name)
        motor.blocked_at = scenario.spec.blocked_at_percent if scenario else None
        effective = target
        pos = motor.position
        if motor.blocked_at is not None:
            limit = float(motor.blocked_at)
            if (pos < limit <= target) or (target <= limit < pos):
                effective = limit
        motor.blocked = False
        motor.start_pos, motor.started, motor.target = pos, now, effective
        motor.running = effective != pos
        motor.direction = 0 if effective > pos else 1 if effective < pos else motor.direction
        motor.source = source
        motor.cause = CAUSE_TARGET_REACHED if not motor.running else CAUSE_EXPLICIT

    def _stop(self, motor: _Motor, now: float) -> None:
        self._settle(motor, now)
        motor.running = False
        motor.start_pos = motor.position
        motor.source, motor.cause = SRC_NETWORK, CAUSE_EXPLICIT

    def _handle(self, raw: bytes, now: float) -> None:
        parsed = _decode(raw)
        if parsed is None:
            self.ignored_requests += 1
            return
        if parsed.dest == 0:  # group request: SOURCE = GroupID
            members = self._groups.get(parsed.src)
            if members is None or parsed.cmd not in (CMD_STOP, CMD_MOVETO):
                self.ignored_requests += 1
                return
            for motor in members:
                self._control(motor, parsed, now)
            return
        motor = self._by_address.get(parsed.dest)
        if motor is None or parsed.src != self._controller:
            self.ignored_requests += 1
            return
        if self._scenario("offline", motor.name) is not None:
            self.ignored_requests += 1
            return
        if parsed.cmd in (CMD_STOP, CMD_MOVETO):
            self._control(motor, parsed, now)
        elif parsed.cmd in (CMD_GET_POS, CMD_GET_STATUS) and not parsed.data:
            self._schedule_reply(motor, parsed.cmd)
        else:
            self.ignored_requests += 1

    def _control(self, motor: _Motor, parsed: _Parsed, now: float) -> None:
        if self._scenario("offline", motor.name) is not None:
            return
        if parsed.cmd == CMD_STOP:
            self._stop(motor, now)
            return
        if len(parsed.data) != 4 or parsed.data[3] != 0:
            self.ignored_requests += 1
            return
        kind, value = parsed.data[0], parsed.data[1] | parsed.data[2] << 8
        if kind == 0:
            target = 100.0
        elif kind == 1:
            target = 0.0
        elif kind == 4 and value <= 100:
            target = float(value)
        else:
            self.ignored_requests += 1
            return
        self._start_move(motor, target, SRC_NETWORK, now)

    def _reply_frame(self, motor: _Motor, kind: int) -> bytes:
        self._settle(motor, self._clock.monotonic())
        if kind == CMD_GET_POS:
            percent = round(motor.position)
            pulses = percent * 10
            data = bytes([pulses & 255, pulses >> 8, percent, 0, 0xFF])
            return _encode(motor.address, self._controller, CMD_POST_POS, data)
        status = 1 if motor.running else 2 if motor.blocked else 0
        data = bytes([status, motor.direction, motor.source, motor.cause])
        return _encode(motor.address, self._controller, CMD_POST_STATUS, data)

    def _schedule_reply(self, motor: _Motor, request_kind: int) -> None:
        silence = self._scenario("silence", motor.name)
        if silence is not None:
            self._consume(silence)
            return
        delay = self.profile.response_latency_seconds
        if self.profile.jitter_seconds:
            delay += self._rng.uniform(-self.profile.jitter_seconds, self.profile.jitter_seconds)
        late = self._scenario("late_reply", motor.name)
        if late is not None:
            delay += late.spec.delay_seconds
            self._consume(late)
        task = asyncio.ensure_future(self._deliver(motor, request_kind, max(0.0, delay)))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _deliver(self, motor: _Motor, request_kind: int, delay: float) -> None:
        await self._clock.sleep(self._scaled(delay))
        if not self._open:
            return
        frame = self._reply_frame(motor, request_kind)
        coalesce = self._scenario("coalesce", motor.name)
        if coalesce is not None:
            other = CMD_GET_STATUS if request_kind == CMD_GET_POS else CMD_GET_POS
            frame += self._reply_frame(motor, other)
            self._consume(coalesce)
        bad = self._scenario("bad_checksum", motor.name)
        if bad is not None:
            frame = frame[:-1] + bytes([frame[-1] ^ 0xFF])
            self._consume(bad)
        fragment = self._scenario("fragment", motor.name)
        size = 1 if fragment is not None else self.profile.chunk_size
        if fragment is not None:
            self._consume(fragment)
        chunks = [frame] if size <= 0 else [frame[i : i + size] for i in range(0, len(frame), size)]
        for index, chunk in enumerate(chunks):
            if index:
                await self._clock.sleep(self._scaled(self.profile.chunk_gap_seconds))
            if not self._open:
                return
            self._queue.put_nowait(chunk)

    # ---- comparison entry point
    @staticmethod
    def compare(real_trace: "SdnTrace", simulated_trace: "SdnTrace",
                comparison_config: Optional["ComparisonConfig"] = None) -> "SdnFidelityScore":
        return compare_traces(real_trace, simulated_trace, comparison_config)


# ------------------------------------------------------------------ trace schemas and recording
class SdnTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t: float = Field(ge=0)
    direction: Literal["tx", "rx"]
    raw: bytes
    chunk: int = Field(0, ge=0)
    backend: Literal["real", "simulated"]
    session_id: str
    connection_generation: int = Field(ge=1)
    decoded: Optional[dict[str, Any]] = None
    correlation: Optional[int] = Field(None, ge=0)

    @field_validator("raw", mode="before")
    @classmethod
    def _hex(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return bytes.fromhex(value)
            except ValueError:
                raise ValueError("invalid hexadecimal bytes") from None
        return value

    @field_serializer("raw")
    def _to_hex(self, value: bytes) -> str:
        return value.hex()


class SdnTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    trace_id: str
    backend: Literal["real", "simulated"]
    profile: str
    config_hash: str
    seed: Optional[int] = None
    time_scale: Optional[float] = None
    software_version: str = SOFTWARE_VERSION
    timing_profile_version: Optional[str] = None
    initial_state: dict[str, Any] = {}
    events: list[SdnTraceEvent] = []
    terminal_state: dict[str, Any] = {}
    started_at: datetime
    ended_at: Optional[datetime] = None
    complete: bool = False
    cleanup_ok: bool = False

    @field_validator("started_at", "ended_at")
    @classmethod
    def _aware(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _ordered(self) -> "SdnTrace":
        times = [e.t for e in self.events]
        if times != sorted(times):
            raise ValueError("trace events must be in monotonic order")
        if self.complete and self.ended_at is None:
            raise ValueError("a complete trace requires ended_at")
        return self


class SdnRecorder:
    """Append-safe recorder used at the SdnApi backend boundary for both real and simulated runs."""

    def __init__(self, backend: Literal["real", "simulated"], clock: Clock, profile: str, config_hash: str,
                 seed: Optional[int] = None, time_scale: Optional[float] = None,
                 timing_profile_version: Optional[str] = None, directory: Optional[str | os.PathLike[str]] = None) -> None:
        self.backend = backend
        self._clock = clock
        self.profile, self.config_hash = profile, config_hash
        self.seed, self.time_scale, self.timing_version = seed, time_scale, timing_profile_version
        self.session_id = uuid.uuid4().hex
        self.trace_id = f"{backend}-{clock.now().strftime('%Y%m%dT%H%M%S')}-{self.session_id[:8]}"
        self._events: list[SdnTraceEvent] = []
        self._t0 = clock.monotonic()
        self._started = clock.now()
        self._initial: dict[str, Any] = {}
        self._correlation: Optional[int] = None
        self._requests = 0
        self._directory = Path(directory) if directory else None
        self._handle: Any = None
        self.finished: Optional[SdnTrace] = None

    @property
    def events(self) -> list[SdnTraceEvent]:
        return self._events

    def start(self, initial_state: Optional[dict[str, Any]] = None) -> None:
        self._initial = dict(initial_state or {})
        self._t0 = self._clock.monotonic()
        if self._directory is not None:
            self._directory.mkdir(parents=True, exist_ok=True)
            path = self._directory / f"{self.trace_id}.jsonl"
            self._handle = open(path, "a", encoding="utf-8", newline="\n")
            _restrict(path)
            self._line({"type": "header", "schema_version": TRACE_SCHEMA_VERSION, "trace_id": self.trace_id,
                        "backend": self.backend, "profile": self.profile, "initial_state": self._initial})

    def _line(self, payload: dict[str, Any]) -> None:
        if self._handle is not None:
            self._handle.write(json.dumps(payload, sort_keys=True) + "\n")
            self._handle.flush()

    def _add(self, direction: Literal["tx", "rx"], raw: bytes, generation: int, chunk: int) -> int:
        event = SdnTraceEvent(t=max(0.0, self._clock.monotonic() - self._t0), direction=direction, raw=raw, chunk=chunk,
                              backend=self.backend, session_id=self.session_id,
                              connection_generation=generation, correlation=self._correlation)
        self._events.append(event)
        self._line({"type": "event", **event.model_dump(mode="json")})
        return len(self._events) - 1

    def record_tx(self, raw: bytes, generation: int) -> int:
        self._correlation = self._requests
        self._requests += 1
        return self._add("tx", raw, generation, 0)

    def record_rx(self, raw: bytes, generation: int, chunk: int = 0) -> int:
        return self._add("rx", raw, generation, chunk)

    def annotate(self, index: int, decoded: dict[str, Any]) -> None:
        event = self._events[index]
        event.decoded = {**(event.decoded or {}), **decoded}
        self._line({"type": "annotation", "index": index, "decoded": decoded})

    def finish(self, terminal_state: Optional[dict[str, Any]] = None, cleanup_ok: bool = True) -> SdnTrace:
        trace = SdnTrace(trace_id=self.trace_id, backend=self.backend, profile=self.profile,
                         config_hash=self.config_hash, seed=self.seed, time_scale=self.time_scale,
                         timing_profile_version=self.timing_version, initial_state=self._initial,
                         events=list(self._events), terminal_state=terminal_state or {},
                         started_at=self._started, ended_at=self._clock.now(), complete=True,
                         cleanup_ok=cleanup_ok)
        if self._handle is not None:
            self._line({"type": "footer", "complete": True, "cleanup_ok": cleanup_ok})
            self._handle.close()
            self._handle = None
            path = self._directory / f"{self.trace_id}.trace.json"  # type: ignore[operator]
            atomic_write_text(path, trace.model_dump_json(indent=1))
            _restrict(path)
        self.finished = trace
        return trace

    @property
    def abandoned(self) -> bool:
        return self.finished is None


def _restrict(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_trace(path: str | os.PathLike[str]) -> SdnTrace:
    return SdnTrace.model_validate_json(Path(path).read_text(encoding="utf-8"))


def recorder_for(config: Any, backend: Literal["real", "simulated"], clock: Clock, base_dir: str | os.PathLike[str],
                 profile: str = "st30") -> Optional[SdnRecorder]:
    """Build a recorder from a validated SystemConfig, or None when recording is disabled."""
    sdn = config.sdn
    if not sdn.recording.enabled:
        return None
    from config import resolve_path

    sim = sdn.simulation if backend == "simulated" else None
    return SdnRecorder(backend, clock, profile, config_fingerprint(config), seed=sim.seed if sim else None,
                       time_scale=sim.time_scale if sim else None,
                       timing_profile_version=TIMING_PROFILES[sim.timing_profile].version if sim else None,
                       directory=resolve_path(base_dir, sdn.recording.directory))


# ------------------------------------------------------------------ fidelity comparison
class ComparisonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    weight_sequence: float = 0.20
    weight_wire: float = 0.25
    weight_value: float = 0.25
    weight_timing: float = 0.20
    weight_outcome: float = 0.10
    position_tolerance_percent: float = Field(3.0, gt=0)
    pulse_tolerance: float = Field(50.0, gt=0)
    first_response_tolerance_seconds: float = Field(0.05, gt=0)
    interval_tolerance_seconds: float = Field(0.10, gt=0)
    initial_position_tolerance_percent: float = Field(2.0, ge=0)
    minimum_overall: float = 0.90
    minimum_sequence: float = 0.95
    minimum_wire: float = 0.95

    @model_validator(mode="after")
    def _weights(self) -> "ComparisonConfig":
        total = (self.weight_sequence + self.weight_wire + self.weight_value + self.weight_timing + self.weight_outcome)
        if abs(total - 1.0) > 1e-9:
            raise ValueError("weights must sum to 1")
        return self


class SdnFidelityScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    valid: bool
    real_trace_id: str
    simulated_trace_id: str
    reasons: list[str] = []
    components: Optional[dict[str, float]] = None
    overall: Optional[float] = None
    matched_events: int = 0
    expected_events: int = 0
    unmatched_real: list[str] = []
    unmatched_simulated: list[str] = []
    max_timing_error_seconds: Optional[float] = None
    max_value_error: Optional[float] = None
    mismatches: list[str] = []
    hard_failures: list[str] = []
    accepted: Optional[bool] = None

    @model_validator(mode="after")
    def _consistent(self) -> "SdnFidelityScore":
        if self.valid:
            if self.components is None or self.overall is None:
                raise ValueError("a valid comparison requires component and overall scores")
            for value in [*self.components.values(), self.overall]:
                if not 0.0 <= value <= 1.0:
                    raise ValueError("scores must be in 0..1")
        else:
            if self.components is not None or self.overall is not None or not self.reasons:
                raise ValueError("an invalid comparison has reasons and no scores")
        return self


@dataclass
class _Frame:
    t_first: float
    t_last: float
    raw: bytes
    valid: bool
    corr: Optional[int]
    parsed: Optional[_Parsed]

    @property
    def signature(self) -> tuple[Any, ...]:
        return (self.parsed.cmd, self.parsed.src) if self.parsed else ("invalid", len(self.raw))


def _rx_frames(trace: SdnTrace) -> list[_Frame]:
    stream = b""
    spans: list[tuple[int, int, SdnTraceEvent]] = []
    for event in trace.events:
        if event.direction == "rx":
            spans.append((len(stream), len(stream) + len(event.raw), event))
            stream += event.raw

    def event_at(offset: int) -> SdnTraceEvent:
        for start, end, event in spans:
            if start <= offset < end:
                return event
        return spans[-1][2]

    frames = []
    for start, end, valid, raw in _scan_stream(stream):
        first, last = event_at(start), event_at(end - 1)
        frames.append(_Frame(first.t, last.t, raw, valid, last.correlation, _decode(raw)))
    return frames


def _tx_frames(trace: SdnTrace) -> list[_Frame]:
    return [_Frame(e.t, e.t, e.raw, _decode(e.raw) is not None, e.correlation, _decode(e.raw))
            for e in trace.events if e.direction == "tx"]


def _lcs_pairs(a: list[tuple[Any, ...]], b: list[tuple[Any, ...]]) -> list[tuple[int, int]]:
    rows, cols = len(a), len(b)
    table = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(cols - 1, -1, -1):
            table[i][j] = table[i + 1][j + 1] + 1 if a[i] == b[j] else max(table[i + 1][j], table[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < rows and j < cols:
        if a[i] == b[j]:
            pairs.append((i, j))
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def _tolerance_score(error: float, tolerance: float) -> float:
    return max(0.0, 1.0 - abs(error) / tolerance)


def _preflight(real: SdnTrace, sim: SdnTrace, cfg: ComparisonConfig) -> list[str]:
    reasons = []
    if real.backend != "real" or sim.backend != "simulated":
        reasons.append("traces must be one real and one simulated trace")
    if not real.complete or not sim.complete:
        reasons.append("both traces must be complete")
    if real.profile != sim.profile:
        reasons.append("motor/profile identity differs")
    if sim.time_scale != 1.0:
        reasons.append("simulated trace time_scale must be 1.0")
    if not real.events or not sim.events:
        reasons.append("a trace has no events")
    elif [e.raw for e in real.events if e.direction == "tx"] != [e.raw for e in sim.events if e.direction == "tx"]:
        reasons.append("ordered request sequences differ")
    for name, state in real.initial_state.items():
        other = sim.initial_state.get(name)
        if other is None:
            reasons.append(f"initial state for {name} missing from simulated trace")
        elif abs(float(state) - float(other)) > cfg.initial_position_tolerance_percent:
            reasons.append(f"initial position for {name} differs beyond tolerance")
    return reasons


def compare_traces(real: SdnTrace, sim: SdnTrace, config: Optional[ComparisonConfig] = None) -> SdnFidelityScore:
    cfg = config or ComparisonConfig()
    base = dict(real_trace_id=real.trace_id, simulated_trace_id=sim.trace_id)
    reasons = _preflight(real, sim, cfg)
    if reasons:
        return SdnFidelityScore(valid=False, reasons=reasons, **base)

    real_rx, sim_rx = _rx_frames(real), _rx_frames(sim)
    real_tx, sim_tx = _tx_frames(real), _tx_frames(sim)
    mismatches: list[str] = []
    unmatched_real: list[str] = []
    unmatched_sim: list[str] = []
    matched_events = len(real_tx)
    expected_events = len(real_tx)
    wire_scores: list[float] = []
    value_scores: list[float] = []
    timing_scores: list[float] = []
    max_timing = 0.0
    max_value = 0.0

    for index, (rtx, stx) in enumerate(zip(real_tx, sim_tx)):
        group_real = [f for f in real_rx if f.corr == index]
        group_sim = [f for f in sim_rx if f.corr == index]
        pairs = _lcs_pairs([f.signature for f in group_real], [f.signature for f in group_sim])
        expected_events += max(len(group_real), len(group_sim))
        matched_events += len(pairs)
        used_r = {p[0] for p in pairs}
        used_s = {p[1] for p in pairs}
        unmatched_real += [f"request {index}: missing {group_real[i].signature}" for i in range(len(group_real)) if i not in used_r]
        unmatched_sim += [f"request {index}: extra {group_sim[j].signature}" for j in range(len(group_sim)) if j not in used_s]
        value_scores += [0.0 for i in range(len(group_real)) if i not in used_r]
        previous_r, previous_s = rtx.t_last, stx.t_last
        for i, j in pairs:
            fr, fs = group_real[i], group_sim[j]
            same_len = len(fr.raw) == len(fs.raw)
            if fs.valid and fr.valid and same_len:
                wire = sum(fr.raw[k] == fs.raw[k] for k in range(9)) / 9.0
            else:
                wire = 0.0
            if wire < 1.0:
                mismatches.append(f"request {index} frame {fr.signature}: header bytes differ or checksum invalid")
            wire_scores.append(wire)
            if fr.parsed and fs.parsed and fr.valid and fs.valid:
                for name, error in _value_errors(fr.parsed, fs.parsed, cfg):
                    value_scores.append(error[0])
                    if error[1] is not None:
                        max_value = max(max_value, error[1])
                    if error[0] < 1.0:
                        mismatches.append(f"request {index} {name}: score {error[0]:.2f}")
            else:
                value_scores.append(0.0)
            request_error = (fr.t_first - rtx.t_last) - (fs.t_first - stx.t_last)
            chunk_error = (fr.t_last - fr.t_first) - (fs.t_last - fs.t_first)
            previous_error = (fr.t_first - previous_r) - (fs.t_first - previous_s)
            for error, tolerance in ((request_error, cfg.first_response_tolerance_seconds),
                                     (chunk_error, cfg.first_response_tolerance_seconds),
                                     (previous_error, cfg.interval_tolerance_seconds)):
                timing_scores.append(_tolerance_score(error, tolerance))
                max_timing = max(max_timing, abs(error))
            previous_r, previous_s = fr.t_last, fs.t_last
    for k in range(1, len(real_tx)):  # polling cadence between consecutive requests
        error = (real_tx[k].t_first - real_tx[k - 1].t_first) - (sim_tx[k].t_first - sim_tx[k - 1].t_first)
        timing_scores.append(_tolerance_score(error, cfg.interval_tolerance_seconds))
        max_timing = max(max_timing, abs(error))
    if real.events and sim.events:  # terminal-response timing
        error = (real.events[-1].t - real.events[0].t) - (sim.events[-1].t - sim.events[0].t)
        timing_scores.append(_tolerance_score(error, cfg.interval_tolerance_seconds))
        max_timing = max(max_timing, abs(error))

    sequence = matched_events / expected_events if expected_events else 1.0
    wire = sum(wire_scores) / len(wire_scores) if wire_scores else (1.0 if not (unmatched_real or unmatched_sim) else 0.0)
    value = sum(value_scores) / len(value_scores) if value_scores else 1.0
    timing = sum(timing_scores) / len(timing_scores) if timing_scores else 1.0
    outcome, outcome_mismatches = _outcome_score(real.terminal_state, sim.terminal_state, cfg)
    mismatches += outcome_mismatches
    components = {"sequence": _clamp(sequence), "wire": _clamp(wire), "value": _clamp(value),
                  "timing": _clamp(timing), "outcome": _clamp(outcome)}
    overall = _clamp(cfg.weight_sequence * components["sequence"] + cfg.weight_wire * components["wire"]
                     + cfg.weight_value * components["value"] + cfg.weight_timing * components["timing"]
                     + cfg.weight_outcome * components["outcome"])

    hard: list[str] = []
    if any(not f.valid for f in sim_rx):
        hard.append("simulated trace contains an invalid checksum/frame")
    if any(not f.valid for f in real_rx):
        hard.append("real trace contains an invalid checksum/frame")
    if not (real.cleanup_ok and sim.cleanup_ok):
        hard.append("cleanup incomplete")
    if components["sequence"] < cfg.minimum_sequence:
        hard.append("sequence score below threshold")
    if components["wire"] < cfg.minimum_wire:
        hard.append("wire score below threshold")
    if overall < cfg.minimum_overall:
        hard.append("overall score below threshold")
    return SdnFidelityScore(valid=True, components=components, overall=overall, matched_events=matched_events,
                            expected_events=expected_events, unmatched_real=unmatched_real,
                            unmatched_simulated=unmatched_sim, max_timing_error_seconds=max_timing,
                            max_value_error=max_value, mismatches=mismatches, hard_failures=hard,
                            accepted=not hard, **base)


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 12)


def _value_errors(real: _Parsed, sim: _Parsed, cfg: ComparisonConfig) -> list[tuple[str, tuple[float, Optional[float]]]]:
    if real.cmd == CMD_POST_POS and len(real.data) >= 5 and len(sim.data) >= 5:
        percent_error = abs(real.data[2] - sim.data[2])
        pulse_error = abs((real.data[0] | real.data[1] << 8) - (sim.data[0] | sim.data[1] << 8))
        return [("position_percent", (_tolerance_score(percent_error, cfg.position_tolerance_percent), float(percent_error))),
                ("pulse_count", (_tolerance_score(pulse_error, cfg.pulse_tolerance), float(pulse_error))),
                ("ip_index", (1.0 if real.data[4] == sim.data[4] else 0.0, None))]
    if real.cmd == CMD_POST_STATUS and len(real.data) >= 4 and len(sim.data) >= 4:
        names = ("status", "direction", "source", "cause")
        return [(n, (1.0 if real.data[i] == sim.data[i] else 0.0, None)) for i, n in enumerate(names)]
    return [("payload", (1.0 if real.data == sim.data else 0.0, None))]


def _outcome_score(real: dict[str, Any], sim: dict[str, Any], cfg: ComparisonConfig) -> tuple[float, list[str]]:
    checks, passed, notes = 0, 0, []
    for name, state in real.items():
        other = sim.get(name)
        if isinstance(state, dict):
            for key, value in state.items():
                checks += 1
                got = other.get(key) if isinstance(other, dict) else None
                if key == "position" and isinstance(value, (int, float)) and isinstance(got, (int, float)):
                    ok = abs(value - got) <= cfg.position_tolerance_percent
                else:
                    ok = value == got
                passed += ok
                if not ok:
                    notes.append(f"terminal {name}.{key}: real={value!r} simulated={got!r}")
        else:
            checks += 1
            ok = state == other
            passed += ok
            if not ok:
                notes.append(f"terminal {name}: real={state!r} simulated={other!r}")
    return (passed / checks if checks else 1.0), notes
