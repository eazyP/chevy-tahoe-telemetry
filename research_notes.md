# Research notes and limitations

## Sources used

- SAE J1979 defines standardized diagnostic modes for emission-related data. The 2002 incorporated copy documents Mode 01 supported-PID bitmaps and says the next `$20` block is requested only when the preceding bitmap advertises it: <https://law.resource.org/pub/us/cfr/ibr/005/sae.j1979.2002.pdf>
- SAE's J1979 catalog describes the scope as vehicle emission-related data and names Mode 01 current powertrain data: <https://saemobilus.sae.org/standards/j1979_199709-e-e-diagnostic-test-modes>
- ELM Electronics' ELM327 family datasheet is the command reference behind reset, echo/linefeed/space settings, protocol selection, and protocol description. Adapter clones may not behave identically: <https://www.elmelectronics.com/wp-content/uploads/2016/07/ELM327L_Data_Sheet.pdf>
- EPA's OBD overview explains that OBD monitors emission-related systems and stores DTCs when faults are detected: <https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P100LW9G.TXT>
- EPA inspection guidance explains readiness states and why recently cleared systems may not yet be ready: <https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P1002KRN.TXT>
- pySerial documents `serial.Serial` and port enumeration; enumeration order and descriptive data are platform-dependent: <https://pyserial.readthedocs.io/en/latest/tools.html> and <https://pyserial.readthedocs.io/en/stable/pyserial_api.html>
- Python 3.11 documents Tkinter's event-driven and threading model: <https://docs.python.org/3.11/library/tkinter.html#threading-model>

## Design decisions

- The application sends `ATSP0` for automatic detection and asks `ATDP` for the adapter's description. `VPW` sends `ATSP2`; it is a user-selectable fallback, not an assertion that every 2004 Tahoe/ECU/adapter combination will negotiate identically.
- Supported PIDs are discovered in 32-PID blocks beginning at `0100`. The next block is queried only if the continuation bit is present. Requested values that are absent from the resulting set stay `Unsupported`.
- Polling, connection, and diagnostic operations run on tracked worker threads. Queues are drained by Tk's `after` callback; workers do not mutate widgets. Disconnect requests are nonblocking, and transport closure serializes with command I/O.
- DTC decoding retains any syntactically valid generic code even when the small bundled description dictionary has no entry.
- Demo mode is deterministic and is not a model of exact engine behavior. Its purpose is UI evaluation and repeatable software testing.

## Limitations

- No hardware or vehicle testing was performed. Automated tests use fake serial objects and deterministic demo data.
- Generic OBD-II primarily covers engine/powertrain emissions information. ABS, SRS/airbag, body, theft, chassis, and manufacturer-enhanced data are not guaranteed.
- PID support is ECU-dependent. In particular, an older flex-fuel vehicle may not expose fuel type, ethanol percentage, module voltage, fuel level, or every fuel-trim PID through generic Mode 01.
- Multi-frame and unusual clone-adapter responses vary. The parser accepts ordinary ELM text replies and common 11-bit CAN header lines, but it is not a universal ISO-TP/J1939 or manufacturer-specific diagnostic stack.
- Permanent DTC support (Mode 0A) was introduced after early OBD-II implementations and may return no data on this model year. The UI reports that group as unavailable; stored or pending communication failures fail the scan explicitly rather than appearing clean.
- Mode 04 behavior is controlled by the vehicle ECU. Clearing can erase freeze-frame/diagnostic context and reset readiness monitors; it never fixes the underlying fault.
