# curtain_control.py Program Specification
### Brad Larson
### 2026-10-02

## Table of Contents

- [Introduction](#introduction)
- [Creator Interview](#creator-interview)
- [Specification Description](#specification-description)
- [Program Generation Process](#program-generation-process)
- [Program Generation Report](#program-generation-report)
- [Program](#program)
- [Functional Requirements](#functional-requirements)
- [Tests](#tests)
- [Issues](#issues)

## Introduction

`curtain_control.py` shall replace the existing Node.js CurtainControl server with a Python FastAPI service for operating Somfy SDN curtains through an RS-485 serial adapter. It preserves the existing device commands, SDN packet format, serial settings, and scheduled-operation capability. It deliberately excludes the existing static HTML, jQuery, and Socket.IO browser interface.

The service is started with the path to one JSON configuration file as a required command-line argument. That file is the sole persistent source of configuration; the program shall not require, connect to, or depend on an external SQL database. The FastAPI HTTP API is the programmatic control surface for automation clients and administration.

Inputs are command-line options, the JSON configuration document, HTTP API requests, time/celestial events, and RS-485 serial input. Outputs are validated HTTP responses, SDN frames written to the serial adapter, structured logs, and scheduling activity.

## Creator Interview

### Creator Interview Transcripts

#### Existing-program review and migration requirements

**Date**: 2026-10-02  
**Creator**: Brad Larson  
**Interviewer**: Codex  

**Transcript**:

**Q:** What behavior does the existing program provide?  
**A:** It controls Somfy SDN curtains and groups over RS-485, presents web and Socket.IO controls, stores motors and groups in MySQL, and has scheduling support.

**Q:** What implementation change is required?  
**A:** Convert the Node server to a Python FastAPI server with similar functionality.

**Q:** What is the storage change?  
**A:** Remove the dependency on an external SQL database. System configuration is in a JSON file specified as a command-line parameter.

**Q:** Should the existing UI be retained?  
**A:** No interface is required. The new server is headless.

**Template value replacement table:**

| Template value | Replacement |
|---|---|
| `{{program_file_name}}` | `curtain_control.py` |
| `{{program_name}}` | `curtain_control` |
| `{{author_name}}` | Brad Larson |
| `{{date}}` | 2026-10-02 |

**AI text generation instructions expansion table:**

| Instruction topic | Evidence / answer | Resulting specification |
|---|---|---|
| Purpose, inputs, outputs, and processing | The existing server handles SDN commands, serial I/O, configuration, and scheduling. | Implement a headless FastAPI service using local JSON configuration and an RS-485 transport. |
| Storage | The creator requires a JSON file named at the command line and no external SQL database. | Load, validate, and atomically persist one local JSON configuration document; do not include a database driver. |
| User interface | The creator specified no interface. | Do not serve static files, browser pages, or Socket.IO. Expose documented HTTP APIs only. |

## Specification Description

This document directs implementation and verification of `curtain_control.py`. It is the source of truth for the new Python service. “No interface” means no browser UI or WebSocket/Socket.IO UI; REST endpoints remain necessary to provide the server’s control function.

When a requirement conflicts with undocumented legacy behavior, this specification takes precedence. The existing JavaScript source is reference material for compatible SDN commands and data fields, not for carrying forward defects.

## Program Generation Process

For each implementation iteration, the generation agent shall:

1. Read this specification and inspect relevant existing implementation and tests.
2. Plan the smallest coherent change, mapping it to requirement IDs.
3. Implement typed Python code, documentation, and tests together.
4. Run formatting, linting if configured, and the applicable unit/integration tests.
5. Record the change, results, risks, and unresolved items in the Program Generation Report.
6. Do not add SQL, browser assets, Socket.IO, or undocumented hardware behavior without an explicit specification update.

The agent shall use dependency injection or a transport abstraction so protocol and API tests run without physical serial hardware. It shall never send test commands to physical curtains unless an explicitly configured integration environment is being used.

## Program Generation Report

### Initial specification creation

- **Date**: 2026-10-02
- **Request**: Create a program specification for a FastAPI replacement of the Node CurtainControl server, using a command-line JSON configuration file and no UI or external SQL database.
- **Status**: Specification created; implementation has not started.

Future reports shall include the request, plan, requirement mapping, changed files, test commands/results, critique, and whether another iteration is needed.

## Program

### Program Description

The program is a long-running FastAPI process deployed near the RS-485 adapter (for example, on a Raspberry Pi). At startup it parses the configuration-file argument, validates the JSON document, opens the configured serial device, and starts scheduled actions. HTTP callers can inspect configuration and issue curtain actions. The program encodes each accepted action as a Somfy SDN frame and writes it to the serial connection.

Quality attributes are safety (reject malformed or unsupported commands before serial writes), predictable configuration, observable failures, and testability without hardware.

### Use Cases

| Use case ID | Use case description | Scenario description | Behavior |
|---|---|---|---|
| UC-001 | Start service | Operator launches the server with a JSON path. | Validate configuration, initialize serial transport, expose API, and start scheduler. |
| UC-002 | Operate a motor | Automation sends an action for a configured motor. | Validate target/action, construct SDN frame, write serial frame, return result. |
| UC-003 | Operate a group | Automation sends an open/close action for a configured group. | Address the group according to SDN semantics and write its command. |
| UC-004 | Set a motor position | Automation requests a percent position or jog action. | Validate the value/range, construct the compatible move packet, and write it. |
| UC-005 | Read/update configuration | Administrator reads or updates motors, groups, or schedules through HTTP. | Validate the whole configuration and atomically replace the JSON file. |
| UC-006 | Run schedule | A cron or celestial event becomes due. | Evaluate condition/configuration and execute its configured action once. |

### Program Structure

| Module / object | Responsibilities |
|---|---|
| `curtain_control.py` | CLI parsing, application construction, lifespan startup/shutdown, and Uvicorn entry point. |
| `config.py` | Pydantic configuration models; JSON load, validation, and atomic write. |
| `api.py` | FastAPI routes, request/response models, exception-to-HTTP mapping. |
| `service.py` | Target lookup, action validation, scheduler dispatch, and serial-write coordination. |
| `sdn_protocol.py` | Command enums and pure functions that encode SDN messages/checksums. |
| `serial_transport.py` | `pyserial` adapter and testable transport protocol. |
| `scheduler.py` | Cron and sunrise/sunset calculation, next-event calculation, and cancellable background loop. |

**Control flow:**

```text
CLI JSON path -> configuration validation -> FastAPI lifespan -> serial transport
HTTP request -> API validation -> curtain service -> SDN encoder -> RS-485 serial write
schedule event -> scheduler -> curtain service -> SDN encoder -> RS-485 serial write
```

### API Contract

The exact route naming may be refined during implementation, but the following resource behavior is required:

| Method and route | Behavior |
|---|---|
| `GET /health` | Return service health and serial readiness without operating a curtain. |
| `GET /config` | Return the validated in-memory configuration with no credentials. |
| `PUT /config` | Validate and atomically replace the complete JSON configuration; reload dependent runtime state safely. |
| `GET /motors` and `GET /groups` | Return configured motors or groups. |
| `POST /actions` | Accept a target type/address or configured name plus action (`up_limit`, `down_limit`, `percent`, `jog`, `lock`, `unlock`, or `stop` where implemented); validate and execute it. |

Successful command responses shall indicate acceptance/completion status and action metadata, never expose raw internal exceptions. Invalid request data returns HTTP 422; unknown targets/actions return 404/422 as appropriate; serial unavailable/write failures return HTTP 503.

### JSON Configuration

The required command-line form is:

```text
python -m curtain_control --config /etc/curtain-control/config.json
```

The document shall be UTF-8 JSON and include schema version, serial settings, site location used by celestial schedules, motors, groups, and schedules. Addresses may be JSON integers or `0x`-prefixed strings, but the loader shall normalize them to integers in the valid 24-bit range.

```json
{
  "schema_version": 1,
  "serial": {
    "port": "/dev/ttyUSB0",
    "baudrate": 4800,
    "bytesize": 8,
    "parity": "odd",
    "stopbits": 1
  },
  "location": { "latitude": 47.6062, "longitude": -122.3321, "timezone": "America/Los_Angeles" },
  "motors": [
    { "address": "0x0671E4", "name": "Stairs East", "description": "", "type": "ST30 RS485", "install": "2026-01-01", "angle": 0, "distance": 0 }
  ],
  "groups": [
    { "address": "0x010110", "name": "Main Floor", "description": "", "devices": ["Stairs East"] }
  ],
  "schedules": [
    { "id": "weekday-open", "timer": "cron", "expression": "45 5 * * 1-5", "action": { "command": "up_limit", "target_type": "group", "target": "Main Floor" } }
  ]
}
```

The implementation shall reject duplicate names or addresses, group members that do not refer to configured motors, malformed schedules, invalid coordinates/timezones, invalid address ranges, and invalid serial settings. File replacement shall use a temporary file in the same directory followed by an atomic rename. The original configuration must remain intact if validation or writing fails.

### SDN Protocol Compatibility

The encoder shall preserve the legacy protocol’s supported operations and packet rules:

- SDN device type `ST30` (`0x02`) and source address `0x000001` unless made configurable later.
- 24-bit source/destination addressing and group addressing convention used by the existing program.
- Commands: move, move-to, stop, motor position query, and lock operations represented by the existing `sdn-protocol.js` command enum.
- Movement modes: down limit, up limit, incremental position, count position, and percent.
- Inverted protocol fields and a 16-bit checksum over all bytes except the two checksum bytes.
- Serial settings default to 4,800 baud, 8 data bits, odd parity, one stop bit.

Incoming serial data shall be logged and may be parsed/validated when framing is implemented. Receiving a malformed frame shall not crash the process or affect later output. Full response parsing is not required for the first version because the legacy application treats serial write completion as action completion.

### Scheduling

Schedules shall support the legacy timer concepts: a one-time ISO date/time, Unix-millisecond timestamp, cron expression, and celestial `sunrise`/`sunset` with millisecond offset. Each schedule must declare one action. The scheduler computes the next due event in the configured timezone, sleeps interruptibly, and recomputes after execution or configuration reload. It must log scheduler errors and continue evaluating later events.

Moon events and legacy hard-coded/test alternating commands are out of scope unless explicitly configured and tested in a later revision.

### Program Environment

**Credentials**

No database credentials are used. The configuration file contains operational details only and should be readable/writable only by the service account when it contains site-sensitive information.

**Libraries**

- Python 3.11 or later.
- `fastapi` and `uvicorn` for the ASGI HTTP server.
- `pydantic` for request/configuration validation.
- `pyserial` for RS-485 serial access.
- `croniter` for cron next-event calculations.
- `astral` for timezone-aware sunrise/sunset calculations.
- `pytest`, `pytest-asyncio`, and FastAPI `TestClient`/`httpx` for testing.

**Standards**

- Type annotate public code and use Pydantic models at configuration/API boundaries.
- Use Python `logging`; do not log raw configuration unnecessarily or silently discard serial errors.
- Keep SDN encoding pure and byte-for-byte unit tested.
- Provide a `requirements.txt` or `pyproject.toml`, a sample configuration that contains no production-specific values, and deployment instructions for a Python systemd service.

## Prompts

No LLM prompts or in-context-learning files are part of the runtime program. Implementation agents shall use this specification, the legacy JavaScript modules, and test fixtures as their implementation context.

## Functional Requirements

| Requirement ID | Requirement description | Requirement verification |
|---|---|---|
| FR-001 | Start only when `--config` identifies a readable, valid JSON file. | Missing, unreadable, malformed, and invalid-schema files cause a clear nonzero startup failure. |
| FR-002 | Do not connect to or require MySQL, SQLite, or any external SQL database. | Dependency/configuration inspection and startup test show no database dependency or connection. |
| FR-003 | Load motors, groups, serial settings, location, and schedules from JSON. | Valid fixture is normalized and exposed through service/config APIs. |
| FR-004 | Persist configuration changes atomically to the same JSON file. | Update test verifies valid replacement and preservation after write/validation failure. |
| FR-005 | Encode supported SDN actions compatibly with legacy packet rules. | Golden-byte tests cover motor/group up, down, percent, jog, lock/unlock, and stop. |
| FR-006 | Use configured 4,800/8/odd/1 serial defaults and report serial failures safely. | Mock transport verifies settings/writes; unavailable transport yields HTTP 503 and logs error. |
| FR-007 | Provide headless REST control and no static web UI or Socket.IO dependency. | API tests succeed; package/file inspection confirms no browser or Socket.IO assets. |
| FR-008 | Validate action targets and values before serial writes. | Invalid action/target/range tests return 4xx and assert zero writes. |
| FR-009 | Support one-time, timestamp, cron, sunrise, and sunset schedules from JSON. | Deterministic clock/location tests verify next-event selection and dispatch. |
| FR-010 | Shut down cleanly. | Lifespan test verifies scheduler cancellation and serial close. |

## Tests

### Unit Tests

- SDN frame golden tests for every supported action, including field inversion, destination addressing, payload, and checksum.
- Address parsing tests for decimal, hexadecimal, boundaries, and invalid values.
- Pydantic configuration tests for required fields, duplicate addresses/names, invalid group membership, malformed schedule, and invalid timezone/location.
- Atomic JSON persistence tests using temporary directories.
- Action validation tests proving invalid payloads cannot reach the transport.
- Scheduler next-event tests with fixed time/location for cron, date, timestamp, sunrise, sunset, offsets, and past events.

### Integration Tests

- Start the FastAPI app with a temporary valid configuration and fake serial transport; verify `/health`, `/config`, `/motors`, and `/groups`.
- POST each supported `/actions` request and verify the exact frame captured by the fake transport.
- PUT `/config`, verify disk replacement and runtime scheduler reload; submit invalid configuration and verify no replacement.
- Simulate transport open/write failure and verify structured 503 responses and continued API availability.

### End-to-End Tests

- On a non-production test rig with a permitted RS-485 adapter, start using the systemd/CLI command and verify serial opening, one known-safe command transmission, and clean shutdown.
- Verify a configured scheduled action fires once at its deterministic test time. Do not use unattended tests against installed curtains without explicit operator approval.

## General Program Structure

### Dependency-injected application services

`create_app(config_path, transport_factory, clock)` shall construct the FastAPI application. Production uses `pyserial`; tests inject a fake transport and controllable clock. This prevents test code from requiring an RS-485 device.

### Local configuration boundary

All file reads/writes occur in the configuration repository. The rest of the application receives validated models rather than arbitrary JSON dictionaries. This replaces the former MySQL pool and SQL CRUD endpoints.

## Program Capabilities

1. Control configured Somfy SDN motors and groups through RS-485.
2. Report service health and configuration through HTTP.
3. Update local configuration safely through HTTP.
4. Run configured cron and solar schedules.
5. Operate without a browser UI, Socket.IO, or external SQL service.

## Issues

### Open Issues

- Authentication/authorization and network exposure policy for the control API have not been specified. Until defined, deployment must restrict network access (for example, localhost, firewall, or reverse proxy).
- Whether group membership should be purely descriptive or expanded into individual motor commands is not specified; preserve legacy group-address commands initially.
- The desired treatment of legacy moon events, response parsing, and motor-position feedback is not specified and is out of scope for the initial implementation.
- The desired serial device path and production JSON configuration values must be supplied during deployment.

### Resolved Issues

- External MySQL configuration and SQL CRUD are replaced by one local JSON configuration file passed with `--config`.
- Browser pages, jQuery, static-file serving, and Socket.IO are excluded from the replacement service.
