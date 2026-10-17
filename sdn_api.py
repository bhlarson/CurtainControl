"""SDN protocol codec and API. Frame layout follows JavaScript `SomfyMsg` (spec: compatibility controls)."""
from __future__ import annotations

import asyncio
import heapq
import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, AsyncIterator, Callable, Literal, Optional, Union

from pydantic import (BaseModel, ConfigDict, Field, field_serializer, field_validator,
                      model_validator)

from clock import Clock, SystemClock
from config import SdnConfig
from models import (MovementRequest, SdnError, SdnFrameError, SdnTimeoutError,  # noqa: F401
                    SdnTransportError, SdnValidationError)
from sdn_sim import SdnRecorder, SdnSim, SdnTrace

MSG_OVERHEAD = 11
MAX_FRAME_LENGTH = 32
MAX_DATA_LENGTH = MAX_FRAME_LENGTH - MSG_OVERHEAD
MAX_ADDRESS = 0xFFFFFF
ACK_MASK, EXT_MASK, LEN_MASK = 0x80, 0x40, 0x3F  # assumption recorded in implementation report
REQUEST_NODE_TYPE = 0x02  # JavaScript ST30 device byte (master -> ST30)
REPLY_NODE_TYPE = 0x20  # ST30 -> master (high nibble source type)
KNOWN_NODE_BYTES = (REQUEST_NODE_TYPE, REPLY_NODE_TYPE)


class Command(IntEnum):
    CTRL_MOVE = 0x01
    CTRL_STOP = 0x02
    CTRL_MOVETO = 0x03
    CTRL_MOVEOF = 0x04
    CTRL_WINK = 0x05
    GET_MOTOR_POSITION = 0x0C
    POST_MOTOR_POSITION = 0x0D
    GET_MOTOR_STATUS = 0x0E
    POST_MOTOR_STATUS = 0x0F
    NACK = 0x6F
    ACK = 0x7F


class MoveType(IntEnum):
    DOWN_LIMIT = 0x00
    UP_LIMIT = 0x01
    PERCENT = 0x04


STATUS_NAMES = {0: "stopped", 1: "running", 2: "blocked", 3: "locked"}
DIRECTION_NAMES = {0: "down", 1: "up", 0xFF: "unknown"}
SOURCE_NAMES = {0: "internal", 1: "network", 2: "local_ui"}
# Cause codes are provisional (spec names them without values); unknown values are retained numerically.
CAUSE_NAMES = {0x01: "target_reached", 0x02: "explicit_command", 0x03: "wink",
               0x11: "obstacle", 0x12: "over_current", 0x13: "thermal", 0x31: "timeout"}


def _check_u24(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SdnValidationError(f"{name} must be an integer")
    if not 0 <= value <= MAX_ADDRESS:
        raise SdnValidationError(f"{name} must be in 0..0xFFFFFF")
    return value


def sdn_msg(source_address: int, destination_address: int, command: int,
            message_data: bytes | bytearray | memoryview = b"") -> bytes:
    """Pure equivalent of JavaScript SomfyMsg; returns one complete immutable frame."""
    source = _check_u24(source_address, "source_address")
    destination = _check_u24(destination_address, "destination_address")
    if isinstance(command, bool) or not isinstance(command, int):
        raise SdnValidationError("command must be an integer")
    try:
        Command(command)
    except ValueError:
        raise SdnValidationError("unsupported command identifier") from None
    if not isinstance(message_data, (bytes, bytearray, memoryview)):
        raise SdnValidationError("message_data must be bytes-like")
    data = bytes(message_data)
    if len(data) > MAX_DATA_LENGTH:
        raise SdnValidationError("message_data exceeds 21 bytes")

    length = MSG_OVERHEAD + len(data)
    frame = bytearray(length)
    frame[0] = ~command & 0xFF
    frame[1] = ~length & 0xFF
    frame[2] = ~REQUEST_NODE_TYPE & 0xFF
    frame[3:6] = source.to_bytes(3, "big")  # JavaScript: MSB first, not complemented
    frame[6:9] = bytes(~b & 0xFF for b in destination.to_bytes(3, "little"))
    for index, byte in enumerate(data):
        frame[9 + index] = ~byte & 0xFF
    checksum = sum(frame[: length - 2]) & 0xFFFF
    frame[length - 2] = checksum >> 8
    frame[length - 1] = checksum & 0xFF
    return bytes(frame)


def move_data(move: MoveType, value: int = 0) -> bytes:
    return bytes((int(move), value & 0xFF, (value >> 8) & 0xFF, 0))


STOP_DATA = b"\x00"


def encode_requests(request: MovementRequest, controller_address: int = 1) -> list[bytes]:
    """Frames for every wire destination in the request (one group frame, or one per member)."""
    caps = request.capabilities
    if request.action == "stop":
        command, data = Command.CTRL_STOP, STOP_DATA
    else:
        command = Command.CTRL_MOVETO
        if request.mode == "up_limit":
            data = move_data(MoveType.UP_LIMIT)
        elif request.mode == "down_limit":
            data = move_data(MoveType.DOWN_LIMIT)
        elif request.mode == "percent":
            data = move_data(MoveType.PERCENT, request.percent or 0)
        else:  # pragma: no cover - guarded by the model validator
            raise SdnValidationError("unsupported movement mode")
        if request.mode in ("up_limit", "down_limit") and not caps.limits:
            raise SdnValidationError("limit movement is not supported by this motor")
        if request.mode == "percent" and not caps.percent:
            raise SdnValidationError("percentage movement is not supported by this motor")
    if request.group_address is not None:
        if not caps.group_command:
            raise SdnValidationError("group command is not supported")
        return [sdn_msg(request.group_address, 0, command, data)]
    return [sdn_msg(controller_address, member.address, command, data) for member in request.members]


def encode_request(request: MovementRequest, controller_address: int = 1) -> bytes:
    frames = encode_requests(request, controller_address)
    if len(frames) != 1:
        raise SdnValidationError("request addresses more than one wire destination")
    return frames[0]


def build_query(command: Command, address: int, controller_address: int = 1) -> bytes:
    if command not in (Command.GET_MOTOR_POSITION, Command.GET_MOTOR_STATUS):
        raise SdnValidationError("unsupported query")
    if _check_u24(address, "address") == 0:
        raise SdnValidationError("a query must address a motor, not zero or broadcast")
    return sdn_msg(controller_address, address, command, b"")


def _decode_fields(raw: bytes) -> dict:
    size = len(raw)
    if not MSG_OVERHEAD <= size <= MAX_FRAME_LENGTH:
        raise SdnFrameError("frame length out of range")
    length_byte = ~raw[1] & 0xFF
    if length_byte & EXT_MASK:
        raise SdnFrameError("reserved EXT flag is set")
    if length_byte & LEN_MASK != size:
        raise SdnFrameError("declared length does not match frame size")
    node_byte = ~raw[2] & 0xFF
    if node_byte not in KNOWN_NODE_BYTES:
        raise SdnFrameError("unsupported node type")
    checksum = (raw[size - 2] << 8) | raw[size - 1]
    if sum(raw[: size - 2]) & 0xFFFF != checksum:
        raise SdnFrameError("checksum mismatch")
    return {
        "command": ~raw[0] & 0xFF,
        "ack_requested": bool(length_byte & ACK_MASK),
        "node_type": node_byte,
        "source_address": int.from_bytes(raw[3:6], "big"),
        "destination_address": int.from_bytes(bytes(~b & 0xFF for b in raw[6:9]), "little"),
        "payload": bytes(~b & 0xFF for b in raw[9 : size - 2]),
        "checksum": checksum,
    }


class SdnFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    raw: bytes
    command: int = Field(ge=0, le=0xFF)
    ack_requested: bool = False
    node_type: int = Field(ge=0, le=0xFF)
    source_address: int = Field(ge=0, le=MAX_ADDRESS)
    destination_address: int = Field(ge=0, le=MAX_ADDRESS)
    payload: bytes
    checksum: int = Field(ge=0, le=0xFFFF)
    received_at: datetime
    received_monotonic: float = 0.0

    @field_validator("raw", "payload", mode="before")
    @classmethod
    def _from_hex(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                return bytes.fromhex(value)
            except ValueError:
                raise ValueError("invalid hexadecimal bytes") from None
        return value

    @field_validator("received_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_serializer("raw", "payload")
    def _to_hex(self, value: bytes) -> str:
        return value.hex()

    @model_validator(mode="after")
    def _agree(self) -> "SdnFrame":
        try:
            fields = _decode_fields(self.raw)
        except SdnFrameError as error:
            raise ValueError(str(error)) from None
        for name, expected in fields.items():
            if getattr(self, name) != expected:
                raise ValueError(f"field {name} disagrees with raw bytes")
        return self

    @property
    def command_name(self) -> Optional[str]:
        try:
            return Command(self.command).name
        except ValueError:
            return None


def decode_frame(raw: bytes, received_at: Optional[datetime] = None, received_monotonic: float = 0.0) -> SdnFrame:
    """Validate one complete frame; raises SdnFrameError for any defect."""
    raw = bytes(raw)
    fields = _decode_fields(raw)
    return SdnFrame(raw=raw, received_at=received_at or datetime.now(timezone.utc),
                    received_monotonic=received_monotonic, **fields)


class FrameParser:
    """Bounded incremental framer: fragments, coalescing, noise, bad frames, and stale partials."""

    def __init__(self, clock: Optional[Clock] = None, max_buffer: int = 4096,
                 incomplete_expiry: float = 1.0) -> None:
        self._clock = clock or SystemClock()
        self._max = max_buffer
        self._expiry = incomplete_expiry
        self._buffer = bytearray()
        self._incomplete_since: Optional[float] = None
        self.dropped_bytes = 0
        self.rejected_frames = 0

    @property
    def buffered(self) -> bytes:
        return bytes(self._buffer)

    def feed(self, data: bytes) -> list[SdnFrame]:
        now = self._clock.monotonic()
        if self._buffer and self._incomplete_since is not None and now - self._incomplete_since > self._expiry:
            self.dropped_bytes += len(self._buffer)
            self._buffer.clear()
            self._incomplete_since = None
        self._buffer += data
        if len(self._buffer) > self._max:
            excess = len(self._buffer) - self._max
            del self._buffer[:excess]
            self.dropped_bytes += excess
        frames: list[SdnFrame] = []
        buf = self._buffer
        pos = 0
        while pos < len(buf):
            if len(buf) - pos < 3:
                break
            length_byte = ~buf[pos + 1] & 0xFF
            length = length_byte & LEN_MASK
            if (length_byte & EXT_MASK or not MSG_OVERHEAD <= length <= MAX_FRAME_LENGTH
                    or (~buf[pos + 2] & 0xFF) not in KNOWN_NODE_BYTES):
                pos += 1
                continue
            if len(buf) - pos < length:
                break
            try:
                frames.append(decode_frame(bytes(buf[pos : pos + length]), self._clock.now(), now))
            except SdnFrameError:
                self.rejected_frames += 1
                pos += 1
                continue
            pos += length
        if pos:
            self.dropped_bytes += pos - sum(len(f.raw) for f in frames)
            del buf[:pos]
        if buf:
            if self._incomplete_since is None or frames:
                self._incomplete_since = now
        else:
            self._incomplete_since = None
        return frames


class MotorFeedback(BaseModel):
    """Decoded observation with receipt identity (spec: preserved across the protocol boundary)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    address: int = Field(ge=1, le=MAX_ADDRESS)
    kind: Literal["position", "status"]
    position_percent: Optional[int] = Field(None, ge=0, le=100)
    pulse_count: Optional[int] = Field(None, ge=0, le=0xFFFF)
    ip_index: Optional[int] = Field(None, ge=0, le=0xFF)
    motor_status: Optional[Literal["stopped", "running", "blocked", "locked"]] = None
    direction: Optional[Literal["down", "up", "unknown"]] = None
    command_source: Optional[Literal["internal", "network", "local_ui"]] = None
    cause_code: Optional[int] = Field(None, ge=0, le=0xFF)
    cause: Optional[str] = None
    received_at: datetime
    received_monotonic: float = Field(ge=0)
    source: Literal["query", "unsolicited"]
    connection_generation: int = Field(ge=1)
    frame_sequence: int = Field(ge=1)

    @field_validator("received_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "MotorFeedback":
        if self.kind == "position" and (self.position_percent is None or self.motor_status is not None):
            raise ValueError("position feedback requires a percentage and no status fields")
        if self.kind == "status" and (self.motor_status is None or self.position_percent is not None):
            raise ValueError("status feedback requires status fields and no percentage")
        return self

    @property
    def identity(self) -> tuple[int, int]:
        return (self.connection_generation, self.frame_sequence)


def decode_feedback(frame: SdnFrame, *, source: Literal["query", "unsolicited"],
                    connection_generation: int, frame_sequence: int) -> Optional[MotorFeedback]:
    """Decode a supported position/status report; other frames yield None. Invalid payloads raise SdnFrameError."""
    common = dict(address=frame.source_address, received_at=frame.received_at,
                  received_monotonic=frame.received_monotonic, source=source,
                  connection_generation=connection_generation, frame_sequence=frame_sequence)
    data = frame.payload
    try:
        if frame.command == Command.POST_MOTOR_POSITION:
            if len(data) < 5:
                raise SdnFrameError("position report too short")
            percent = data[2]
            if percent > 100:
                raise SdnFrameError("position percentage out of range")
            return MotorFeedback(kind="position", position_percent=percent,
                                 pulse_count=data[0] | (data[1] << 8), ip_index=data[4], **common)
        if frame.command == Command.POST_MOTOR_STATUS:
            if len(data) < 4:
                raise SdnFrameError("status report too short")
            status, direction, command_source, cause = data[0], data[1], data[2], data[3]
            if status not in STATUS_NAMES or direction not in DIRECTION_NAMES or command_source not in SOURCE_NAMES:
                raise SdnFrameError("unsupported status values")
            return MotorFeedback(kind="status", motor_status=STATUS_NAMES[status],
                                 direction=DIRECTION_NAMES[direction],
                                 command_source=SOURCE_NAMES[command_source], cause_code=cause,
                                 cause=CAUSE_NAMES.get(cause), **common)
    except ValueError as error:
        raise SdnFrameError(str(error)) from None
    return None


@dataclass(frozen=True)
class SdnFrameEvent:
    frame: SdnFrame


@dataclass(frozen=True)
class SdnFeedbackEvent:
    feedback: MotorFeedback


@dataclass(frozen=True)
class SdnLinkEvent:
    state: Literal["connected", "disconnected"]
    generation: int
    reason: Optional[str] = None


SdnEvent = Union[SdnFrameEvent, SdnFeedbackEvent, SdnLinkEvent]
PRIORITY_CONTROL, PRIORITY_QUERY = 0, 1


@dataclass
class _Waiter:
    expected: int
    address: int
    future: "asyncio.Future[MotorFeedback]"


class SdnApi:
    """Selects exactly one byte backend and owns encoding, bus arbitration, queries, parsing, and tracing."""

    SdnMsg = staticmethod(sdn_msg)
    decode_frame = staticmethod(decode_frame)
    encode_request = staticmethod(encode_request)

    def __init__(self, backend_config: SdnConfig, serial_interface: Any = None, simulator: Any = None,
                 recorder: Optional[SdnRecorder] = None, clock: Optional[Clock] = None) -> None:
        if backend_config.mode == "real":
            if serial_interface is None or simulator is not None or isinstance(serial_interface, SdnSim):
                raise SdnValidationError("real mode requires exactly one serial interface and no simulator")
            backend = serial_interface
        else:
            if simulator is None or serial_interface is not None or not isinstance(simulator, SdnSim):
                raise SdnValidationError("simulated mode requires exactly one SdnSim and no serial interface")
            backend = simulator
        for name in ("open", "close", "read", "write"):
            if not callable(getattr(backend, name, None)):
                raise SdnValidationError("backend does not implement the byte-transport contract")
        self._config = backend_config
        self._backend = backend
        self._simulator = simulator
        self._recorder = recorder
        self._clock = clock or SystemClock()
        self._controller = backend_config.controller_address
        self._min_interval = backend_config.bus_min_interval_seconds
        self._parser = FrameParser(self._clock, backend_config.receive_buffer_bytes,
                                   backend_config.incomplete_frame_expiry_seconds)
        self._generation = 0
        self._frame_seq = 0
        self._connected = False
        self._receive_task: Optional[asyncio.Task[None]] = None
        self._recorder_started = False
        self._waiter: Optional[_Waiter] = None
        self._bus_busy = False
        self._bus_waiters: list[tuple[int, int, asyncio.Future[None]]] = []
        self._bus_seq = itertools.count()
        self._last_activity = float("-inf")
        self._subscribers: list[asyncio.Queue[SdnEvent]] = []
        self._chunk_index = 0
        self.invalid_replies = 0
        self.timeouts = 0
        self.dropped_events = 0
        self.trace: Optional[SdnTrace] = None

    # ---- properties
    @property
    def mode(self) -> str:
        return self._config.mode

    @property
    def connection_generation(self) -> int:
        return self._generation

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def recorder(self) -> Optional[SdnRecorder]:
        return self._recorder

    # ---- lifecycle
    async def start(self, initial_state: Optional[dict[str, Any]] = None) -> None:
        if self._receive_task is not None and self._connected:
            return
        try:
            await self._backend.open()
        except SdnTransportError:
            raise
        except Exception as error:
            raise SdnTransportError(f"backend open failed: {type(error).__name__}") from None
        self._generation += 1
        self._connected = True
        self._parser = FrameParser(self._clock, self._config.receive_buffer_bytes,
                                   self._config.incomplete_frame_expiry_seconds)
        self._chunk_index = 0
        if self._recorder is not None and not self._recorder_started:
            if initial_state is None and self._simulator is not None:
                initial_state = {name: s["position"] for name, s in self._simulator.snapshot().items()}
            self._recorder.start(initial_state)
            self._recorder_started = True
        self._receive_task = asyncio.ensure_future(self._receive_loop(self._generation))
        self._emit(SdnLinkEvent("connected", self._generation))

    async def _stop_receiving(self) -> bool:
        task, self._receive_task = self._receive_task, None
        clean = True
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        waiter = self._waiter
        if waiter is not None and not waiter.future.done():
            waiter.future.set_exception(SdnTransportError("SDN link closed"))
        self._connected = False
        try:
            await self._backend.close()
        except Exception:
            clean = False
        return clean

    async def stop(self, terminal_state: Optional[dict[str, Any]] = None) -> Optional[SdnTrace]:
        terminal = terminal_state
        if terminal is None and self._simulator is not None:
            terminal = self._simulator.snapshot()
        clean = await self._stop_receiving()
        if self._recorder is not None and self._recorder_started and self._recorder.finished is None:
            self.trace = self._recorder.finish(terminal, cleanup_ok=clean)
        return self.trace

    async def reconnect(self) -> None:
        await self._stop_receiving()
        await self.start()

    # ---- event stream
    def subscribe_events(self, maxsize: int = 256) -> "asyncio.Queue[SdnEvent]":
        queue: asyncio.Queue[SdnEvent] = asyncio.Queue(maxsize)
        self._subscribers.append(queue)
        return queue

    def unsubscribe_events(self, queue: "asyncio.Queue[SdnEvent]") -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def received_frames(self) -> AsyncIterator[SdnEvent]:
        queue = self.subscribe_events()
        try:
            while True:
                yield await queue.get()
        finally:
            self.unsubscribe_events(queue)

    def _emit(self, event: SdnEvent) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self.dropped_events += 1

    def feed_received_data(self, data: bytes) -> list[SdnFrame]:
        return self._parser.feed(data)

    # ---- receive path
    async def _receive_loop(self, generation: int) -> None:
        try:
            while True:
                chunk = await self._backend.read()
                self._last_activity = self._clock.monotonic()
                index: Optional[int] = None
                if self._recorder is not None:
                    index = self._recorder.record_rx(chunk, generation, self._chunk_index)
                self._chunk_index += 1
                for frame in self.feed_received_data(chunk):
                    self._on_frame(frame, index)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._handle_disconnect(generation, error)

    def _on_frame(self, frame: SdnFrame, event_index: Optional[int]) -> None:
        self._frame_seq += 1
        sequence = self._frame_seq
        waiter = self._waiter
        matched = (waiter is not None and not waiter.future.done() and frame.command == waiter.expected
                   and frame.source_address == waiter.address)
        feedback: Optional[MotorFeedback] = None
        try:
            feedback = decode_feedback(frame, source="query" if matched else "unsolicited",
                                       connection_generation=self._generation, frame_sequence=sequence)
        except SdnFrameError:
            self.invalid_replies += 1
        if self._recorder is not None and event_index is not None:
            note: dict[str, Any] = {"command": frame.command_name or f"0x{frame.command:02X}",
                                    "source": frame.source_address, "destination": frame.destination_address,
                                    "payload": frame.payload.hex()}
            if feedback is not None:
                note["feedback"] = feedback.model_dump(mode="json", exclude_none=True,
                                                       include={"kind", "position_percent", "motor_status",
                                                                "direction", "command_source", "cause_code"})
            self._recorder.annotate(event_index, note)
        self._emit(SdnFrameEvent(frame))
        if feedback is None:
            return
        if matched and waiter is not None:
            waiter.future.set_result(feedback)
        self._emit(SdnFeedbackEvent(feedback))

    def _handle_disconnect(self, generation: int, error: BaseException) -> None:
        if generation != self._generation or not self._connected:
            return
        self._connected = False
        reason = f"{type(error).__name__}"
        waiter = self._waiter
        if waiter is not None and not waiter.future.done():
            waiter.future.set_exception(SdnTransportError(f"SDN link lost: {reason}"))
        self._emit(SdnLinkEvent("disconnected", generation, reason))

    # ---- bus arbitration and transmit path
    async def _acquire_bus(self, priority: int) -> None:
        if not self._bus_busy:
            self._bus_busy = True
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._bus_waiters, (priority, next(self._bus_seq), future))
        try:
            await future
        except asyncio.CancelledError:
            if future.done() and not future.cancelled():
                self._release_bus()
            raise

    def _release_bus(self) -> None:
        while self._bus_waiters:
            _, _, future = heapq.heappop(self._bus_waiters)
            if not future.done():
                future.set_result(None)
                return
        self._bus_busy = False

    def _require_connected(self) -> None:
        if not self._connected:
            raise SdnTransportError("SDN link is not connected")

    async def _transmit(self, frame: bytes, guard: Optional[Callable[[], bool]] = None) -> bool:
        wait = self._last_activity + self._min_interval - self._clock.monotonic()
        if wait > 0:
            await self._clock.sleep(wait)
        self._require_connected()
        if guard is not None and not guard():
            return False
        if self._recorder is not None:
            self._recorder.record_tx(frame, self._generation)
        try:
            await self._backend.write(frame)
        except Exception as error:
            self._handle_disconnect(self._generation, error)
            if isinstance(error, SdnTransportError):
                raise
            raise SdnTransportError(f"backend write failed: {type(error).__name__}") from None
        self._last_activity = self._clock.monotonic()
        return True

    async def send(self, request: MovementRequest, guard: Optional[Callable[[], bool]] = None,
                   on_sent: Optional[Callable[[], None]] = None) -> bool:
        """Write the request's frames. `guard` is rechecked on the bus right before each write (False vetoes
        remaining writes); `on_sent` runs synchronously after each completed write. Returns True if any frame was written."""
        frames = encode_requests(request, self._controller)
        self._require_connected()
        await self._acquire_bus(PRIORITY_CONTROL)
        sent = False
        try:
            for frame in frames:
                if not await self._transmit(frame, guard):
                    break
                sent = True
                if on_sent is not None:
                    on_sent()
        finally:
            self._release_bus()
        return sent

    async def _query(self, command: Command, expected: Command, address: int, timeout: float) -> MotorFeedback:
        frame = build_query(command, address, self._controller)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise SdnValidationError("timeout must be positive")
        self._require_connected()
        await self._acquire_bus(PRIORITY_QUERY)
        try:
            future: asyncio.Future[MotorFeedback] = asyncio.get_running_loop().create_future()
            self._waiter = _Waiter(int(expected), address, future)  # registered before the write
            try:
                await self._transmit(frame)
                try:
                    return await self._clock.wait_for(future, timeout)
                except asyncio.TimeoutError:
                    self.timeouts += 1
                    await self._clock.sleep(self._min_interval)  # quiesce before the next query
                    raise SdnTimeoutError(f"no reply from motor 0x{address:06X}") from None
            finally:
                self._waiter = None
                if not future.done():
                    future.cancel()
        finally:
            self._release_bus()

    async def get_position(self, address: int, timeout: float) -> MotorFeedback:
        return await self._query(Command.GET_MOTOR_POSITION, Command.POST_MOTOR_POSITION, address, timeout)

    async def get_status(self, address: int, timeout: float) -> MotorFeedback:
        return await self._query(Command.GET_MOTOR_STATUS, Command.POST_MOTOR_STATUS, address, timeout)
