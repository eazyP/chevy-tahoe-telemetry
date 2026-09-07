# Tahoe Telemetry

A Windows desktop OBD-II dashboard aimed at a 2004 Chevrolet Tahoe 5.3L flex-fuel. It uses Python 3.11, Tkinter/ttk, and a USB ELM327-compatible adapter. It discovers the vehicle's supported Mode 01 PIDs before polling, labels unavailable readings **Unsupported**, and keeps all serial polling off Tk's main thread.

This is a generic OBD-II engine/emissions tool. It does not promise access to ABS, SRS/airbag, body, transfer-case, or other manufacturer-specific modules. Every displayed PID remains dependent on what the connected ECU actually reports.

## Features

- Automatic protocol selection (`ATSP0`) by default, detected-protocol display (`ATDP`), and selectable SAE J1850 VPW fallback (`ATSP2`).
- COM-port enumeration and 9600/38400/57600/115200 baud choices.
- Live readings and rolling numeric charts for RPM, speed, coolant, load, throttle, MAF, intake temperature, module voltage, short/long trims on both banks, fuel level, and ethanol percentage; fuel type is shown as a categorical live value.
- Stored (Mode 03), pending (Mode 07), and permanent (Mode 0A) DTC reads. Communication failures are reported as scan errors rather than clean groups; unsupported permanent-code service is shown as unavailable. Common generic descriptions are included; unfamiliar codes remain visible as `Unknown code`.
- Mode 04 clearing requires typing `CLEAR` and accepting a second readiness-reset warning.
- Timestamped CSV logs, persistent JSON preferences, deterministic no-hardware demo mode, interlocked diagnostic operations, and nonblocking graceful serial/log shutdown.

## Buying an adapter

Choose a reputable **USB** ELM327-compatible adapter that explicitly supports SAE J1850 VPW and Windows 10/11. Prefer a vendor that identifies the USB serial chipset (FTDI, CP210x, or CH340) and provides a signed Windows driver. Extremely cheap adapters often misreport firmware versions or omit older protocols. USB is preferred here over Bluetooth because the application expects a Windows COM port and a stable wired link. Confirm the seller's return policy; no particular adapter has been hardware-validated by this project.

## Install on Windows

1. Install 64-bit Python 3.11 with Tcl/Tk and the Python launcher options enabled.
2. Open PowerShell in this directory:

   ```powershell
   python3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Run `start_tahoe_telemetry.bat`, or:

   ```powershell
   .\.venv\Scripts\python.exe -m tahoe_telemetry
   ```

For a packaged executable:

```powershell
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm tahoe_telemetry.spec
```

The output is `dist\TahoeTelemetry.exe`.

## Safe use

- Park outdoors or in a properly ventilated area, set the parking brake, and keep the cable clear of pedals and steering controls.
- Do not operate or watch a laptop while driving. Use a passenger for moving tests.
- Plug in the adapter with ignition off, then turn the key to RUN. Do not disconnect during a clear operation.
- Treat telemetry as diagnostic information, not proof that a vehicle is safe. Stop the engine for overheating, oil-pressure warnings, fuel leaks, smoke, or abnormal operation.
- Clearing codes does not repair a fault. Mode 04 erases useful diagnostic context and resets emissions readiness monitors; the vehicle may fail an inspection until its drive cycle completes.

## Use

Select the adapter COM port, its baud rate (38400 is a common starting point), and `AUTO`. If automatic negotiation fails on this vehicle, disconnect and try `VPW`. The **Detected** field reports the ELM327's answer to `ATDP`; it is not inferred from the selection.

Enable **Demo** to explore without an adapter. Demo data is seeded and repeatable, includes sample DTCs, and deliberately marks fuel type unsupported. CSV files use local timestamps in filenames and ISO-8601 timestamps in rows. Settings are stored at `%LOCALAPPDATA%\TahoeTelemetry\settings.json`.

## Test and smoke check

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe smoke_check.py
```

The smoke check is deliberately headless and uses only demo data. Neither it nor the automated suite tests an actual Tahoe, ELM327, USB driver, or vehicle network.

## Troubleshooting

- **Access denied:** close other scan tools/serial terminals and reconnect.
- **No response:** verify the key is in RUN, adapter LEDs are on, the COM port and baud are correct, and the adapter supports the selected protocol.
- **Unsupported:** this is expected when the ECU's supported-PID bitmap does not advertise a value. It is not replaced with a guessed number.
- **Sparse/odd values:** clone adapters and multi-ECU replies vary. Try AUTO first and reduce polling load by disconnecting other diagnostic equipment.

See [research_notes.md](research_notes.md) for protocol sources and explicit limitations.
