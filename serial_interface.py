"""Real RS-485 byte transport (pyserial). Knows nothing about SDN or curtains."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from config import SerialConfig
from models import SdnTransportError

_PARITY = {"odd": "O", "even": "E", "none": "N"}
READ_TIMEOUT_SECONDS = 0.1
WRITE_TIMEOUT_SECONDS = 1.0


class SerialInterface:
    def __init__(self, config: SerialConfig, serial_factory: Optional[Callable[..., Any]] = None) -> None:
        self._config = config
        self._factory = serial_factory
        self._port: Any = None
        self._write_lock = asyncio.Lock()
        self._closed = True

    @property
    def is_open(self) -> bool:
        return self._port is not None and not self._closed

    def _open_blocking(self) -> Any:
        factory = self._factory
        if factory is None:
            import serial  # imported lazily so simulated mode never loads pyserial

            factory = serial.Serial
            parity = getattr(serial, "PARITY_" + {"O": "ODD", "E": "EVEN", "N": "NONE"}[_PARITY[self._config.parity]])
            stopbits = serial.STOPBITS_ONE if self._config.stopbits == 1 else serial.STOPBITS_TWO
            bytesize = serial.EIGHTBITS if self._config.bytesize == 8 else serial.SEVENBITS
        else:
            parity, stopbits, bytesize = _PARITY[self._config.parity], self._config.stopbits, self._config.bytesize
        port = factory(port=self._config.port, baudrate=self._config.baudrate, bytesize=bytesize,
                       parity=parity, stopbits=stopbits, timeout=READ_TIMEOUT_SECONDS,
                       write_timeout=WRITE_TIMEOUT_SECONDS, xonxoff=False, rtscts=False, dsrdtr=False)
        if getattr(port, "baudrate", self._config.baudrate) != self._config.baudrate:
            port.close()
            raise OSError("effective baud rate differs from the configured value")
        return port

    async def open(self) -> None:
        if self.is_open:
            return
        try:
            self._port = await asyncio.to_thread(self._open_blocking)
        except Exception as error:
            self._port = None
            raise SdnTransportError(f"cannot open serial port: {type(error).__name__}") from None
        self._closed = False

    async def close(self) -> None:
        self._closed = True
        port, self._port = self._port, None
        if port is not None:
            try:
                await asyncio.to_thread(port.close)
            except Exception:
                pass

    def _read_blocking(self) -> bytes:
        port = self._port
        if port is None:
            raise OSError("port closed")
        waiting = getattr(port, "in_waiting", 0)
        return port.read(waiting or 1)

    async def read(self) -> bytes:
        """Return the next non-empty chunk; raise SdnTransportError on failure or close."""
        while True:
            if self._closed:
                raise SdnTransportError("serial port is closed")
            try:
                chunk = await asyncio.to_thread(self._read_blocking)
            except Exception as error:
                if self._closed:
                    raise SdnTransportError("serial port is closed") from None
                raise SdnTransportError(f"serial read failed: {type(error).__name__}") from None
            if chunk:
                return bytes(chunk)

    def _write_blocking(self, data: bytes) -> None:
        port = self._port
        if port is None:
            raise OSError("port closed")
        written = port.write(data)
        if written is not None and written != len(data):
            raise OSError("short write")
        flush = getattr(port, "flush", None)
        if flush:
            flush()

    async def write(self, data: bytes) -> None:
        """Write one complete frame in a single ordered driver call."""
        if self._closed:
            raise SdnTransportError("serial port is closed")
        async with self._write_lock:
            try:
                await asyncio.to_thread(self._write_blocking, bytes(data))
            except Exception as error:
                raise SdnTransportError(f"serial write failed: {type(error).__name__}") from None
