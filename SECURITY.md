# Security Policy

## Supported version

Security fixes are applied to the latest release on the `main` branch.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use GitHub's **Report a vulnerability** option in the repository Security tab so the report and discussion remain private.

Include the affected version, reproduction steps, impact, and any suggested mitigation. Do not include vehicle owner information, VINs, credentials, or other personal data.

## Vehicle-safety boundary

Tahoe Telemetry is a generic OBD-II engine/emissions diagnostic aid, not a safety certification tool. It does not program control modules. The only destructive diagnostic operation is Mode 04 trouble-code clearing, which requires typed confirmation and a second warning because it erases diagnostic context and resets emissions-readiness monitors.

Test new releases in Demo mode before connecting to a vehicle. Do not interact with the application while driving.
