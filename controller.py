"""CurtainController: owns physical motor state, operations, polling, verification, and live events.

State transitions are synchronous sections of one event loop; serial I/O happens only outside them.
`MovementRequest.percent` at this boundary is the application percentage (0 = open, 100 = closed).
"""
from __future__ import annotations

import asyncio
import collections
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import field_validator, model_validator

from clock import Clock, SystemClock
from config import Inventory, MonitoringConfig, Percent
from models import (FrozenModel, MemberRef, MovementRequest, SdnTimeoutError, SdnTransportError,
                    SdnValidationError)
from sdn_api import MotorFeedback, SdnApi, SdnFeedbackEvent, SdnLinkEvent

Health = Literal["unknown", "online", "stale", "offline"]
Validity = Literal["unknown", "fresh", "stale"]
Motion = Literal["unknown", "stopped", "opening", "closing", "moving"]
Fault = Literal["blocked", "locked", "obstacle", "over_current", "thermal", "timeout"]
OpStatus = Literal["pending", "active", "completed", "failed", "cancelled"]
TERMINAL = ("completed", "failed", "cancelled")
LIVE = ("pending", "active")
FAULT_CAUSES = {"obstacle", "over_current", "thermal", "timeout"}
SEEN_LIMIT = 4096
log = logging.getLogger("curtaincontrol.controller")


class ControllerRequestError(Exception):
    """Request rejected before any state change or SDN write."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class OperationNotFound(KeyError):
    pass


def _replace(model: Any, **updates: Any) -> Any:
    data = {name: getattr(model, name) for name in type(model).model_fields}
    data.update(updates)
    return type(model).model_validate(data)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value


class MotorState(FrozenModel):
    motor_id: str
    session_id: str
    connection_generation: int = 0
    communication_health: Health = "unknown"
    reported_percent: Optional[Percent] = None
    position_validity: Validity = "unknown"
    position_received_at: Optional[datetime] = None
    reported_motion: Motion = "unknown"
    status_validity: Validity = "unknown"
    status_received_at: Optional[datetime] = None
    status_source: Optional[Literal["internal", "network", "local_ui"]] = None
    status_cause: Optional[str] = None
    fault: Optional[Fault] = None
    expected_motion: Optional[Literal["opening", "closing"]] = None
    estimated_percent: Optional[Percent] = None
    active_target_percent: Optional[Percent] = None
    active_operation_id: Optional[str] = None
    consecutive_query_failures: int = 0

    @field_validator("position_received_at", "status_received_at")
    @classmethod
    def _tz(cls, value: Optional[datetime]) -> Optional[datetime]:
        return _aware(value)

    @model_validator(mode="after")
    def _consistent(self) -> "MotorState":
        if self.position_validity != "unknown" and (self.reported_percent is None or self.position_received_at is None):
            raise ValueError("a position observation requires a percentage and receipt time")
        if self.position_validity == "unknown" and self.reported_percent is not None:
            raise ValueError("a reported percentage requires a position validity")
        if self.status_validity != "unknown" and self.status_received_at is None:
            raise ValueError("a status observation requires a receipt time")
        if self.status_validity == "unknown" and (self.reported_motion != "unknown" or self.fault is not None):
            raise ValueError("motion and fault require a status observation")
        if self.communication_health == "online" and self.position_validity == "unknown" and self.status_validity == "unknown":
            raise ValueError("online health requires at least one observation")
        if self.consecutive_query_failures < 0:
            raise ValueError("failure count cannot be negative")
        return self


class MemberOutcome(FrozenModel):
    status: OpStatus
    retry_count: int = 0
    error: Optional[str] = None


class Operation(FrozenModel):
    operation_id: str
    session_id: str
    action: Literal["position", "stop"]
    target_type: Literal["motor", "group"]
    target: str
    requested_percent: Optional[Percent] = None
    status: OpStatus
    revision: int = 1
    members: dict[str, MemberOutcome]
    created_at: datetime
    transmitted_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    error: Optional[str] = None

    @field_validator("created_at", "transmitted_at", "deadline_at", "completed_at")
    @classmethod
    def _tz(cls, value: Optional[datetime]) -> Optional[datetime]:
        return _aware(value)

    @model_validator(mode="after")
    def _consistent(self) -> "Operation":
        if (self.action == "stop") != (self.requested_percent is None):
            raise ValueError("stop has no percentage; position requires one")
        terminal = self.status in TERMINAL
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal operations (and only those) carry a completion time")
        if self.status == "failed" and not self.error:
            raise ValueError("a failed operation requires a safe error code")
        if self.status == "completed" and self.error is not None:
            raise ValueError("a completed operation has no error")
        if self.status == "completed" and any(m.status != "completed" for m in self.members.values()):
            raise ValueError("a completed operation requires every member completed")
        if not self.members:
            raise ValueError("an operation needs at least one member")
        return self


class ControllerEvent(FrozenModel):
    session_id: str
    sequence: int
    kind: Literal["motor_state", "operation", "link"]
    timestamp: datetime
    motor: Optional[MotorState] = None
    operation: Optional[Operation] = None
    detail: Optional[str] = None


class ControllerSnapshot(FrozenModel):
    session_id: str
    sequence: int
    motors: dict[str, MotorState]
    operations: tuple[Operation, ...] = ()


class ControllerSubscription:
    """Initial snapshot plus a bounded live queue; `get()` returns None when a resync is required."""

    def __init__(self, controller: "CurtainController", snapshot: ControllerSnapshot, size: int) -> None:
        self.snapshot = snapshot
        self._controller = controller
        self._queue: asyncio.Queue[Optional[ControllerEvent]] = asyncio.Queue(size)
        self.overflowed = False
        self.closed = False

    def _offer(self, event: ControllerEvent) -> None:
        if self.closed:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.overflowed = True
            while not self._queue.empty():
                self._queue.get_nowait()
            self._queue.put_nowait(None)
            self.close()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._controller._subscriptions.discard(self)
            if self._queue.empty():
                self._queue.put_nowait(None)

    async def get(self) -> Optional[ControllerEvent]:
        return await self._queue.get()

    def get_nowait(self) -> Optional[ControllerEvent]:
        return self._queue.get_nowait()

    def empty(self) -> bool:
        return self._queue.empty()


@dataclass
class _Obs:
    pos_mono: Optional[float] = None
    pos_gen: int = 0
    status_mono: Optional[float] = None
    status_gen: int = 0
    last_poll: float = float("-inf")
    revision: int = 0


@dataclass
class _Member:
    status: str = "pending"
    tx_mono: Optional[float] = None
    generation: int = 0
    deadline: Optional[float] = None
    retry_count: int = 0
    retry_at: Optional[float] = None
    error: Optional[str] = None


@dataclass
class _Record:
    op: Operation
    target: Optional[int]
    request: MovementRequest
    members: dict[str, _Member] = field(default_factory=dict)


class CurtainController:
    def __init__(self, api: SdnApi, inventory: Inventory, config: MonitoringConfig,
                 clock: Optional[Clock] = None) -> None:
        self._api = api
        self._inventory = inventory
        self._cfg = config
        self._clock = clock or SystemClock()
        self.session_id = ""
        self._started = False
        self._states: dict[str, MotorState] = {}
        self._obs: dict[str, _Obs] = {}
        self._records: collections.OrderedDict[str, _Record] = collections.OrderedDict()
        self._seen: collections.OrderedDict[tuple[int, int], None] = collections.OrderedDict()
        self._subscriptions: set[ControllerSubscription] = set()
        self._sequence = 0
        self._tasks: list[asyncio.Task[None]] = []
        self._sdn_queue: Optional[asyncio.Queue[Any]] = None
        self._wake = asyncio.Event()
        self._last_reconnect = float("-inf")
        self._by_address = {m.address: m.name for m in inventory.config.motors}

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if self._started:
            return
        self.session_id = uuid.uuid4().hex
        self._started = True
        self._sequence = 0
        self._records.clear()
        self._seen.clear()
        self._obs = {name: _Obs() for name in self._inventory.motors}
        generation = self._api.connection_generation
        self._states = {name: MotorState(motor_id=name, session_id=self.session_id, connection_generation=generation)
                        for name in self._inventory.motors}
        self._sdn_queue = self._api.subscribe_events(1024)
        self._tasks = [asyncio.ensure_future(self._feedback_loop()), asyncio.ensure_future(self._monitor())]
        self._wake.set()

    async def close(self) -> None:
        if not self._started:
            return
        self._started = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        if self._sdn_queue is not None:
            self._api.unsubscribe_events(self._sdn_queue)
            self._sdn_queue = None
        for record in list(self._records.values()):
            if record.op.status in LIVE:
                for member_id, member in record.members.items():
                    if member.status in LIVE:
                        self._set_member(record, member_id, "cancelled", "shutdown")
                self._update_op(record)
        for subscription in list(self._subscriptions):
            subscription.close()

    def reload(self, inventory: Inventory) -> None:
        """Adopt a validated inventory: add new motors, cancel work for removed ones. No I/O."""
        removed = set(self._inventory.motors) - set(inventory.motors)
        for record in list(self._records.values()):
            touched = False
            for motor_id in removed & set(record.members):
                if record.members[motor_id].status in LIVE:
                    self._set_member(record, motor_id, "cancelled", "removed")
                    touched = True
            if touched:
                self._update_op(record)
        self._inventory = inventory
        self._by_address = {m.address: m.name for m in inventory.config.motors}
        for motor_id in removed:
            self._states.pop(motor_id, None)
            self._obs.pop(motor_id, None)
        if self._started:
            for motor_id in inventory.motors:
                if motor_id not in self._states:
                    self._states[motor_id] = MotorState(motor_id=motor_id, session_id=self.session_id,
                                                        connection_generation=self._api.connection_generation)
                    self._obs[motor_id] = _Obs()
            self._wake.set()

    def _require_started(self) -> None:
        if not self._started:
            raise ControllerRequestError("not_started", "controller is not running")

    # ------------------------------------------------------------------ queries
    def get_state(self, motor_id: Optional[str] = None) -> MotorState | dict[str, MotorState]:
        if motor_id is None:
            return dict(self._states)
        return self._states[motor_id]

    def get_operation(self, operation_id: str) -> Operation:
        record = self._records.get(operation_id)
        if record is None or record.op.session_id != self.session_id:
            raise OperationNotFound(operation_id)
        return record.op

    def subscribe(self, size: Optional[int] = None) -> ControllerSubscription:
        snapshot = ControllerSnapshot(
            session_id=self.session_id, sequence=self._sequence, motors=dict(self._states),
            operations=tuple(r.op for r in self._records.values() if r.op.status in LIVE))
        subscription = ControllerSubscription(self, snapshot, size or self._cfg.event_queue_size)
        self._subscriptions.add(subscription)
        return subscription

    def _emit(self, kind: str, **payload: Any) -> None:
        self._sequence += 1
        event = ControllerEvent(session_id=self.session_id, sequence=self._sequence, kind=kind,
                                timestamp=self._clock.now(), **payload)
        for subscription in list(self._subscriptions):
            subscription._offer(event)

    def _set_state(self, motor_id: str, **updates: Any) -> bool:
        old = self._states[motor_id]
        new = _replace(old, **updates)
        if new == old:
            return False
        self._states[motor_id] = new
        self._emit("motor_state", motor=new)
        return True

    # ------------------------------------------------------------------ admission
    def _resolve(self, request: MovementRequest) -> tuple[list[str], Optional[int]]:
        ids: list[str] = []
        for ref in request.members:
            config = self._inventory.motors.get(ref.motor_id)
            if config is None:
                raise ControllerRequestError("unknown_motor")
            if config.address != ref.address:
                raise ControllerRequestError("address_mismatch")
            if not config.enabled:
                raise ControllerRequestError("motor_disabled")
            ids.append(ref.motor_id)
        if request.group_id is not None:
            group = self._inventory.groups.get(request.group_id)
            if group is None:
                raise ControllerRequestError("unknown_group")
            if not set(ids) <= set(group.devices):
                raise ControllerRequestError("group_member_mismatch")
            if request.group_address is not None and (group.address != request.group_address or set(ids) != set(group.devices)):
                raise ControllerRequestError("group_member_mismatch")
        elif len(ids) > 1:
            raise ControllerRequestError("group_required")
        target: Optional[int] = None
        if request.action == "position":
            caps = request.capabilities
            if not (caps.position_feedback and caps.status_feedback):
                raise ControllerRequestError("capability", "verified positioning requires position and status feedback")
            target = {"up_limit": 0, "down_limit": 100}.get(request.mode, request.percent)
        return ids, target

    async def submit(self, request: MovementRequest) -> Operation:
        self._require_started()
        ids, target = self._resolve(request)
        if request.action == "position":
            for record in self._records.values():
                if (record.op.status in LIVE and record.op.action == "position" and record.target == target
                        and set(record.members) == set(ids)
                        and all(m.status in LIVE for m in record.members.values())):
                    return record.op
        for motor_id in ids:
            if request.revision < self._obs[motor_id].revision:
                raise ControllerRequestError("stale_revision")
        reason = "cancelled_by_stop" if request.action == "stop" else "superseded"
        superseded = self._supersede(ids, reason)
        for motor_id in ids:
            self._obs[motor_id].revision = request.revision
        now = self._clock.now()
        target_type = "group" if request.group_id else "motor"
        record = _Record(
            op=Operation(operation_id=uuid.uuid4().hex, session_id=self.session_id, action=request.action,
                         target_type=target_type, target=request.group_id or ids[0], requested_percent=target,
                         status="pending", revision=request.revision, created_at=now,
                         members={i: MemberOutcome(status="pending") for i in ids}),
            target=target, request=request, members={i: _Member() for i in ids})
        self._records[record.op.operation_id] = record
        self._emit("operation", operation=record.op)
        if request.action == "position" and not superseded and all(self._satisfied_now(i, target) for i in ids):
            for motor_id in ids:
                self._set_member(record, motor_id, "completed", None)
            self._update_op(record)
            return record.op
        for motor_id in ids:
            self._set_state(motor_id, active_operation_id=record.op.operation_id, active_target_percent=target)
        await self._transmit(record, ids)
        self._trim_history()
        return record.op

    async def stop(self, motor_id: str) -> Operation:
        config = self._inventory.motors.get(motor_id)
        if config is None:
            raise ControllerRequestError("unknown_motor")
        self._require_started()
        request = MovementRequest(action="stop", mode="stop", members=(MemberRef(motor_id=motor_id, address=config.address),),
                                  revision=max(1, self._obs[motor_id].revision), correlation_id=uuid.uuid4().hex)
        return await self.submit(request)

    def _supersede(self, motor_ids: list[str], reason: str) -> bool:
        any_cancelled = False
        for record in list(self._records.values()):
            if record.op.status not in LIVE:
                continue
            touched = False
            for motor_id in motor_ids:
                member = record.members.get(motor_id)
                if member is not None and member.status in LIVE:
                    self._set_member(record, motor_id, "cancelled", reason)
                    touched = any_cancelled = True
            if touched:
                self._update_op(record)
        return any_cancelled

    def _satisfied_now(self, motor_id: str, target: Optional[int]) -> bool:
        state, obs = self._states[motor_id], self._obs[motor_id]
        generation = self._api.connection_generation
        if (state.position_validity != "fresh" or state.status_validity != "fresh" or obs.pos_mono is None
                or obs.status_mono is None or obs.pos_gen != generation or obs.status_gen != generation):
            return False
        if abs(obs.pos_mono - obs.status_mono) > self._cfg.verification_max_skew_seconds:
            return False
        return (state.reported_motion == "stopped" and state.fault is None and target is not None
                and abs((state.reported_percent or 0) - target) <= self._cfg.tolerance_percent)

    # ------------------------------------------------------------------ transmission
    def _wire_requests(self, record: _Record, member_ids: list[str]) -> list[MovementRequest]:
        request = record.request
        caps = request.capabilities
        correlation, revision = request.correlation_id, request.revision
        if request.action == "stop":
            mode, percent_for = "stop", (lambda config: None)
        elif record.target == 0 and caps.limits:
            mode, percent_for = "up_limit", (lambda config: None)
        elif record.target == 100 and caps.limits:
            mode, percent_for = "down_limit", (lambda config: None)
        else:
            mode = "percent"
            percent_for = lambda config: 100 - record.target if config.invert_position else record.target  # noqa: E731
        action = request.action
        configs = {i: self._inventory.motors[i] for i in member_ids}
        group = self._inventory.groups.get(request.group_id) if request.group_id else None
        uniform = len({configs[i].invert_position for i in member_ids}) == 1 or mode != "percent"
        if (request.group_address is not None and group is not None and caps.group_command and uniform
                and set(member_ids) == set(group.devices) == set(record.members)):
            first = configs[member_ids[0]]
            return [MovementRequest(action=action, mode=mode, members=tuple(MemberRef(motor_id=i, address=configs[i].address) for i in member_ids),
                                    group_address=request.group_address, group_id=request.group_id,
                                    percent=percent_for(first), revision=revision, correlation_id=correlation, capabilities=caps)]
        return [MovementRequest(action=action, mode=mode, members=(MemberRef(motor_id=i, address=configs[i].address),),
                                percent=percent_for(configs[i]), revision=revision, correlation_id=correlation, capabilities=caps)
                for i in member_ids]

    async def _transmit(self, record: _Record, member_ids: list[str]) -> None:
        wires = self._wire_requests(record, member_ids)
        failure: Optional[str] = None
        for wire in wires:
            wire_ids = [m.motor_id for m in wire.members]
            if failure is not None:
                for motor_id in wire_ids:
                    if record.members[motor_id].status in LIVE:
                        self._set_member(record, motor_id, "failed", failure)
                continue

            def guard(ids: list[str] = wire_ids) -> bool:
                return record.op.status in LIVE and all(record.members[i].status in LIVE for i in ids)

            def on_sent(ids: list[str] = wire_ids) -> None:
                self._mark_sent(record, ids)

            try:
                await self._api.send(wire, guard=guard, on_sent=on_sent)
            except SdnTransportError:
                failure = "transport_unavailable"
            except SdnValidationError:
                failure = "invalid_request"
            if failure is not None:
                for motor_id in wire_ids:
                    if record.members[motor_id].status in LIVE:
                        self._set_member(record, motor_id, "failed", failure)
        self._update_op(record)
        self._wake.set()

    def _mark_sent(self, record: _Record, motor_ids: list[str]) -> None:
        now = self._clock.monotonic()
        for motor_id in motor_ids:
            member = record.members[motor_id]
            if member.status not in LIVE:
                continue
            member.status, member.tx_mono = "active", now
            member.generation = self._api.connection_generation
            member.deadline = now + self._cfg.travel_deadline_seconds
            member.retry_at = None
            updates: dict[str, Any] = {}
            if record.target is not None:
                reported = self._states[motor_id].reported_percent
                if reported is not None:
                    updates["expected_motion"] = "closing" if record.target > reported else "opening" if record.target < reported else None
            if updates:
                self._set_state(motor_id, **updates)
        deadline = max(m.deadline for m in record.members.values() if m.deadline is not None)
        wall = self._clock.now()
        self._update_op(record, transmitted_at=wall, deadline_at=wall + _seconds(deadline - now))

    # ------------------------------------------------------------------ operation bookkeeping
    def _set_member(self, record: _Record, motor_id: str, status: str, error: Optional[str]) -> None:
        member = record.members[motor_id]
        member.status, member.error = status, error
        member.retry_at = None
        if status in TERMINAL and motor_id in self._states:
            state = self._states[motor_id]
            if state.active_operation_id == record.op.operation_id:
                self._set_state(motor_id, active_operation_id=None, active_target_percent=None, expected_motion=None)

    def _update_op(self, record: _Record, **extra: Any) -> None:
        members = {i: MemberOutcome(status=m.status, retry_count=m.retry_count, error=m.error) for i, m in record.members.items()}
        statuses = {m.status for m in record.members.values()}
        updates: dict[str, Any] = {"members": members, "retry_count": max(m.retry_count for m in record.members.values())}
        if record.op.status in LIVE and statuses <= set(TERMINAL):
            failed = [m for m in record.members.values() if m.status == "failed"]
            cancelled = [m for m in record.members.values() if m.status == "cancelled"]
            if failed:
                status, error = "failed", failed[0].error if len(record.members) == 1 else "member_failed"
            elif cancelled:
                status, error = "cancelled", cancelled[0].error
            else:
                status, error = "completed", None
            updates.update(status=status, error=error or ("verification_failed" if status == "failed" else None),
                           completed_at=self._clock.now())
        elif record.op.status == "pending" and "active" in statuses:
            updates["status"] = "active"
        updates.update(extra)
        new = _replace(record.op, **updates)
        if new != record.op:
            record.op = new
            self._emit("operation", operation=new)

    def _trim_history(self) -> None:
        while len(self._records) > self._cfg.history_limit:
            for operation_id, record in self._records.items():
                if record.op.status in TERMINAL:
                    del self._records[operation_id]
                    break
            else:
                return

    # ------------------------------------------------------------------ feedback
    async def _feedback_loop(self) -> None:
        assert self._sdn_queue is not None
        while True:
            event = await self._sdn_queue.get()
            try:
                if isinstance(event, SdnFeedbackEvent):
                    self._apply_feedback(event.feedback)
                elif isinstance(event, SdnLinkEvent):
                    self._on_link(event)
            except Exception:
                log.exception("event handling failed")

    def _remember(self, identity: tuple[int, int]) -> bool:
        if identity in self._seen:
            return False
        self._seen[identity] = None
        while len(self._seen) > SEEN_LIMIT:
            self._seen.popitem(last=False)
        return True

    def _apply_feedback(self, feedback: MotorFeedback) -> bool:
        if not self._remember(feedback.identity):
            return False
        motor_id = self._by_address.get(feedback.address)
        if motor_id is None or feedback.connection_generation != self._api.connection_generation:
            return False
        config, obs = self._inventory.motors[motor_id], self._obs[motor_id]
        updates: dict[str, Any] = {"communication_health": "online", "consecutive_query_failures": 0,
                                   "connection_generation": feedback.connection_generation}
        if feedback.kind == "position":
            if obs.pos_mono is not None and feedback.received_monotonic < obs.pos_mono:
                return False
            percent = feedback.position_percent or 0
            updates.update(reported_percent=100 - percent if config.invert_position else percent,
                           position_validity="fresh", position_received_at=feedback.received_at)
            obs.pos_mono, obs.pos_gen = feedback.received_monotonic, feedback.connection_generation
        else:
            if obs.status_mono is not None and feedback.received_monotonic < obs.status_mono:
                return False
            fault: Optional[str] = None
            if feedback.motor_status in ("blocked", "locked"):
                fault = feedback.motor_status
            elif feedback.cause in FAULT_CAUSES and feedback.motor_status != "running":
                fault = feedback.cause
            if feedback.motor_status == "running":
                if feedback.direction == "unknown":
                    motion = "moving"
                else:
                    closing = feedback.direction == "down"
                    motion = "closing" if closing != config.invert_position else "opening"
            else:
                motion = "stopped"
            updates.update(reported_motion=motion, status_validity="fresh", status_received_at=feedback.received_at,
                           status_source=feedback.command_source, status_cause=feedback.cause, fault=fault)
            obs.status_mono, obs.status_gen = feedback.received_monotonic, feedback.connection_generation
        changed = self._set_state(motor_id, **updates)
        self._check_operations()
        return changed

    def _on_link(self, event: SdnLinkEvent) -> None:
        if event.state == "disconnected":
            for motor_id, state in list(self._states.items()):
                updates: dict[str, Any] = {"communication_health": "offline"}
                if state.position_validity != "unknown":
                    updates["position_validity"] = "stale"
                if state.status_validity != "unknown":
                    updates["status_validity"] = "stale"
                self._set_state(motor_id, **updates)
            for record in list(self._records.values()):
                if record.op.status in LIVE:
                    for motor_id, member in record.members.items():
                        if member.status in LIVE:
                            self._set_member(record, motor_id, "failed", "transport_unavailable")
                    self._update_op(record)
            self._emit("link", detail="disconnected")
        else:
            for motor_id, state in list(self._states.items()):
                self._obs[motor_id].last_poll = float("-inf")
                updates = {"connection_generation": event.generation}
                if state.communication_health == "offline":
                    updates["communication_health"] = "unknown"
                self._set_state(motor_id, **updates)
            self._emit("link", detail="connected")
            self._wake.set()

    # ------------------------------------------------------------------ verification
    def _verified(self, record: _Record, member: _Member, state: MotorState, obs: _Obs) -> bool:
        tx = member.tx_mono
        if tx is None or obs.status_mono is None or obs.status_mono <= tx or obs.status_gen != member.generation:
            return False
        if state.status_validity != "fresh" or state.reported_motion != "stopped":
            return False
        if record.op.action == "stop":
            return True
        if (obs.pos_mono is None or obs.pos_mono <= tx or obs.pos_gen != member.generation
                or state.position_validity != "fresh"):
            return False
        if abs(obs.pos_mono - obs.status_mono) > self._cfg.verification_max_skew_seconds:
            return False
        return abs((state.reported_percent or 0) - (record.target or 0)) <= self._cfg.tolerance_percent

    def _mismatch_evidence(self, record: _Record, member: _Member, state: MotorState, obs: _Obs) -> bool:
        """Fresh, coherent, post-transmission stopped position that misses the target (and no fault)."""
        if record.op.action != "position" or state.fault is not None:
            return False
        tx = member.tx_mono
        if (tx is None or obs.pos_mono is None or obs.status_mono is None or obs.pos_mono <= tx or obs.status_mono <= tx
                or obs.pos_gen != member.generation or obs.status_gen != member.generation
                or state.position_validity != "fresh" or state.status_validity != "fresh"
                or state.reported_motion != "stopped"):
            return False
        if abs(obs.pos_mono - obs.status_mono) > self._cfg.verification_max_skew_seconds:
            return False
        return abs((state.reported_percent or 0) - (record.target or 0)) > self._cfg.tolerance_percent

    def _check_operations(self) -> None:
        for record in list(self._records.values()):
            if record.op.status not in LIVE:
                continue
            for motor_id, member in record.members.items():
                if member.status != "active" or member.tx_mono is None:
                    continue
                state, obs = self._states[motor_id], self._obs[motor_id]
                if (record.op.action == "position" and state.fault is not None and obs.status_mono is not None
                        and obs.status_mono > member.tx_mono and obs.status_gen == member.generation):
                    self._set_member(record, motor_id, "failed", "motor_fault")
                elif self._verified(record, member, state, obs):
                    self._set_member(record, motor_id, "completed", None)
            self._update_op(record)

    def _check_deadlines(self) -> None:
        now = self._clock.monotonic()
        for record in list(self._records.values()):
            if record.op.status not in LIVE:
                continue
            for motor_id, member in record.members.items():
                if member.status != "active" or member.deadline is None or now < member.deadline:
                    continue
                state, obs = self._states[motor_id], self._obs[motor_id]
                evidence = self._mismatch_evidence(record, member, state, obs)
                if evidence and self._cfg.retry_enabled and member.retry_count < 1:
                    member.retry_at, member.deadline = now + self._cfg.retry_cooldown_seconds, None
                else:
                    self._set_member(record, motor_id, "failed", "position_mismatch" if evidence else "verification_timeout")
            self._update_op(record)

    async def _process_retries(self) -> None:
        now = self._clock.monotonic()
        for record in list(self._records.values()):
            if record.op.status not in LIVE:
                continue
            for motor_id, member in list(record.members.items()):
                if member.status == "active" and member.retry_at is not None and now >= member.retry_at:
                    member.retry_at = None
                    member.retry_count += 1
                    await self._transmit(record, [motor_id])

    # ------------------------------------------------------------------ monitoring
    def _expire_freshness(self) -> None:
        now = self._clock.monotonic()
        for motor_id, state in list(self._states.items()):
            obs = self._obs[motor_id]
            updates: dict[str, Any] = {}
            if state.position_validity == "fresh" and obs.pos_mono is not None \
                    and now - obs.pos_mono > self._cfg.position_freshness_seconds:
                updates["position_validity"] = "stale"
            if state.status_validity == "fresh" and obs.status_mono is not None \
                    and now - obs.status_mono > self._cfg.status_freshness_seconds:
                updates["status_validity"] = "stale"
            if updates and state.communication_health == "online":
                position = updates.get("position_validity", state.position_validity)
                status = updates.get("status_validity", state.status_validity)
                if position != "fresh" and status != "fresh":
                    updates["communication_health"] = "stale"
            if updates:
                self._set_state(motor_id, **updates)

    def _record_failure(self, motor_id: str) -> None:
        failures = self._states[motor_id].consecutive_query_failures + 1
        updates: dict[str, Any] = {"consecutive_query_failures": failures}
        if failures >= self._cfg.offline_failure_threshold:
            updates["communication_health"] = "offline"
        self._set_state(motor_id, **updates)

    async def _poll_motor(self, motor_id: str) -> None:
        address = self._inventory.motors[motor_id].address
        self._obs[motor_id].last_poll = self._clock.monotonic()
        timeout = self._cfg.query_timeout_seconds
        for query in (self._api.get_position, self._api.get_status):
            try:
                feedback = await query(address, timeout)
            except SdnTimeoutError:
                self._record_failure(motor_id)
                continue
            except SdnTransportError:
                return
            except SdnValidationError:
                log.warning("query for %s rejected", motor_id)
                return
            self._apply_feedback(feedback)

    def _active_motors(self) -> set[str]:
        """Motors needing the active cadence: live operations, or reported moving (e.g. a local button press)."""
        active = {i for r in self._records.values() if r.op.status in LIVE
                  for i, m in r.members.items() if m.status in LIVE}
        active |= {i for i, s in self._states.items() if s.reported_motion in ("opening", "closing", "moving")
                   and s.status_validity == "fresh"}
        return active

    async def poll_once(self) -> None:
        """One monitoring pass (also used directly by deterministic tests)."""
        if not self._api.connected:
            self._expire_freshness()
            now = self._clock.monotonic()
            if now - self._last_reconnect >= self._cfg.reconnect_interval_seconds:
                self._last_reconnect = now
                try:
                    await self._api.reconnect()
                except SdnTransportError:
                    log.warning("SDN reconnect failed")
            return
        self._expire_freshness()
        self._check_operations()
        self._check_deadlines()
        await self._process_retries()
        active = self._active_motors()
        now = self._clock.monotonic()
        for motor_id in self._inventory.motors:
            if not self._api.connected:
                break
            if motor_id in active or now - self._obs[motor_id].last_poll >= self._cfg.poll_idle_interval_seconds:
                await self._poll_motor(motor_id)
                self._check_operations()
        self._check_deadlines()

    def _next_expiry(self) -> Optional[float]:
        """Seconds until the earliest fresh observation goes stale (so expiry does not wait for the next poll)."""
        now = self._clock.monotonic()
        waits = []
        for motor_id, state in self._states.items():
            obs = self._obs[motor_id]
            if state.position_validity == "fresh" and obs.pos_mono is not None:
                waits.append(obs.pos_mono + self._cfg.position_freshness_seconds - now)
            if state.status_validity == "fresh" and obs.status_mono is not None:
                waits.append(obs.status_mono + self._cfg.status_freshness_seconds - now)
        return max(0.01, min(waits)) + 0.001 if waits else None

    async def _monitor(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("monitor pass failed")
            interval = (self._cfg.poll_active_interval_seconds if self._active_motors()
                        else self._cfg.poll_idle_interval_seconds)
            expiry = self._next_expiry()
            if expiry is not None:
                interval = min(interval, expiry)
            self._wake.clear()
            try:
                await self._clock.wait_for(self._wake.wait(), interval)
            except asyncio.TimeoutError:
                pass


def _seconds(value: float) -> Any:
    from datetime import timedelta
    return timedelta(seconds=value)
