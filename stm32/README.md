# STM32 firmware

## Current range update (2026-10-15)

At the user's explicit request, both tracking axes now use 500–2500 us PWM.
`TRK LIMITS?` reports `TRK_LIMITS=0500,2500,0500,2500`; the paired Qt worker
requires this contract before accepting control. Manual holds now use the retained
position and bounded TRK steps, without issuing CENTER on every press. After a
firmware reset the position is still UNKNOWN and explicit initial centering is required.
Legacy center-relative UART commands are unchanged for other callers.

The 80 us target step, 24 us / 20 ms ramp, 2-second timeout and PWM-off boot remain.
Keil ARMCC 5.06u5 built with 0 errors / 0 warnings; ST-Link download reported
Verify OK. HEX SHA256:
`20ca1662acbcdf6418464326f76bce172c3d639a9b77a6e66fba899fd43e3d03`.
The installed limits and PWM-off startup were read back without motion commands.
This is a requested electrical control range, not verified mechanical geometry;
no endpoint movement test was performed, as requested. Earlier 600-us TILT clearance
observations remain historical evidence and are not replaced by this readback.
Backup, build, rollback and installation evidence:
`local/gimbal-manual-range-20261015/REPORT.md`.

## Previous hand-tracking firmware (2026-09-30)

The latest UART firmware preserves the last output pulse after stopping. After a
reset, `TRK POS?` returns `TRK_POS=UNKNOWN` and `TRK ARM` rejects movement with
`ERR TRK_POSITION_UNKNOWN`. An explicit `TRK CENTER` initializes the pulses or
ramps from a known position; restarting tracking then continues from the retained
values instead of jumping to 1500 us. Retention is RAM-only command state, not
physical angle feedback, and cannot detect manual movement while PWM is off.

The existing 500–2500 us PAN / 750–2250 us TILT bounds, 24 us per 20 ms ramp and
2-second timeout remain. Keil build and download records report 0 errors,
0 warnings and Verify OK. The latest HEX SHA256 is
`f172dd084a22eb50aa0ff65925b9506a4c2f4c8d35d7ab374b0f04832e0a3b60`.
The Qt application and worker were subsequently updated for delayed feedback;
the user's final observation was that the result was usable with room to improve.
Exact versions, test limits and paired rollback locations are recorded in
`local/gimbal-resume-fix-20260930.md` and the root `HANDOFF.md`.
This documentation sync did not rebuild, flash or repeat hardware tests.

## 2026-09-29 bounded hand tracking (prior stage)

The UART project also accepts an explicit tracking session: `TRK ARM` arms without
PWM output; `TRK P+`, `TRK P-`, `TRK T+`, and `TRK T-` adjust each target by 80 us.
The two TIM3 channels can output together, while actual PWM approaches each target
by at most 24 us every 20 ms. PAN is clamped to 500–2500 us and TILT to 750–2250 us.
`TRK KEEP` refreshes the 2-second tracking deadline, `TRK STOP` stops and disarms,
and `TRK?` returns `TRK=ARMED` or `TRK=OFF`. Any 2-second command gap stops both
axes and disarms. `PAN STOP` and `TILT STOP` also disarm tracking. The existing
manual commands, PING, LED, and UART behavior remain available. Boot stays PWM-off.
The following historical UART-stage section describes the original baseline.

This directory contains the STM32 execution-layer firmware for the RK3568 AI terminal.
UART stage status as of 2026-09-23: firmware flashing, RK3568 UART9 persistent boot,
warm reboot, and physical power-off/power-on acceptance have all passed.
The PC13 blink baseline remains intact. A separate USART1 text-protocol project now
contains the RK3568 UART link; sensors, actuators, MQTT, Qt, AI, vision, and the planned
binary CRC protocol remain out of scope.

## Hardware baseline

- Board evidence: the user's board photo and the matching minimum-system-board material
  under `D:\1stm32\资料`.
- MCU: STM32F103C8T6, Cortex-M3, 64 KiB Flash, 20 KiB RAM.
- Board LED: PC13, active low. In the material, the `2-1 STM32工程模板` wiring diagram
  has no external LED while its source configures PC13 as an output and drives it low.
  The LED component is also visibly adjacent to the `PC13` silkscreen on the user's board.
- Debug interface: SWD through ST-Link. Target power, common ground, and SWD wiring must
  be confirmed before any download.

## Firmware project

`firmware/stm32f103c8t6-minimal/Project.uvprojx` is derived from the tutorial project at
`D:\1stm32\资料\程序源码\STM32Project-有注释版\3-1 LED闪烁`. The timing code comes from
that project; the board-LED pin comes from the matching `2-1 STM32工程模板` material.
The source material remains unchanged.

This original project only toggles LED1 every 500 ms. It intentionally contains no UART
or application-layer functionality and remains the rollback baseline. Do not replace it
with the UART project.

## UART project

`firmware/stm32f103c8t6-uart-link/Project.uvprojx` is a separate, versionable copy of
the previously tested project at `D:\AProject\stm32-uart-link-20260921\firmware`.
That work area's `source-pristine` remains the untouched tutorial example; the original
PC13 blink project above is also unchanged. The UART target is STM32F103C8T6 (Keil
device `STM32F103C8`). USART1 uses PA9 TX and PA10 RX at 115200, 8N1, no flow control.
The LED is on PC13 and is active low. It starts off.

The text protocol uses ASCII commands terminated by `\r\n`:

| Request | Response | Status |
| --- | --- | --- |
| `PING` | `PONG` | Verified on RK3568 ↔ STM32 after flashing this image. |
| `LED?` | `LED=ON` or `LED=OFF` | Both states verified by serial readback after flashing this image. |
| `LED ON` | `OK` | Serial response and `LED=ON` readback passed; user visually confirmed LED on. |
| `LED OFF` | `OK` | Serial response and `LED=OFF` readback passed; user visually confirmed LED off. |
| Other nonempty command | `ERR` | Verified on hardware with `UNKNOWN`. |

The RK3568 smoke-test script is `tools/uart-smoke.py` at the repository root. It sends
one `PING` and one `LED?` through `/dev/ttyS9`. The UART9 M1 boot image has now been
written to the RK3568 boot partition. `/dev/ttyS9` remained available after a warm
reboot and after a user-performed full power-off/power-on cycle; the latter also
passed `PING` and `LED?` readback. The cold-start boot-partition SHA256 still matched
the 64 MiB UART9 candidate listed below.
`ttyFIQ0` remains the Linux debug console and must not be used for this link.
Connect TX to the other board's RX and share GND. Each board
keeps its separately verified power source: do not join ST-Link 3V3 to RK3568 3V3 or
connect 5V to either UART signal.

The binary CRC frame design in `docs/uart-protocol-draft.md` is a future proposal,
not implemented by this firmware.

The new UART project was rebuilt on 2026-09-23 with Keil uVision 5.24a and ARMCC
5.06 update 5 (build 528), target `STM32F103C8`: **0 errors, 0 warnings**.
The build log is `firmware/stm32f103c8t6-uart-link/build-keil-20260923.log` (ignored
by Git). Output files are `Objects/stm32_uart_link.axf` and
`Objects/stm32_uart_link.hex` within the same project directory (also ignored).
Keil reports `Code=2512`, `RO-data=268`, `RW-data=24`, `ZI-data=1104` bytes:
2,804 bytes Flash and 1,128 bytes RAM. With separate user authorization, this image
was downloaded via ST-Link on 2026-09-23. The ignored local log
`firmware/stm32f103c8t6-uart-link/flash-keil-20260923.log` reports erase done,
programming done, verify OK, and application running. The post-flash serial sequence
`PING`, `LED ON`, `LED?`, `LED OFF`, `LED?` passed. On the second demonstration the
user visually confirmed that the PC13 LED turned on and then off. The script held
the on state for 10 seconds; the user did not independently time that interval.
Before any RK3568 permanent boot-image write, a further RAM-only test passed:
25 `PING` exchanges, 10 LED on/off/readback cycles, an unknown command (`ERR`),
an empty line (no reply), and a split `PING` transmission. The final LED state was
`OFF`. The RK3568 original boot partition still matched its backup SHA256 afterward.
After separate user authorization, the 64 MiB UART9 candidate was written to the
RK3568 boot partition and read back with the exact candidate SHA256. The board
warm-rebooted to Linux with Wi-Fi and `/dev/ttyS9` available; the post-reboot boot
partition SHA256 still matched the candidate. Post-write `PING`, `LED ON`, `LED?`,
`LED OFF`, `LED?` passed, followed by 20 PC13 LED on/off cycles over 10.12 seconds,
ending with `LED=OFF` readback. The user separately confirmed seeing the PC13 LED
flash and then remain off during this post-write demonstration.

## Toolchain baseline

- Keil uVision: 5.24a
- Compiler requested by the project: ARMCC 5.06 update 5 (build 528)
- Device configuration: STM32F103C8

Build outputs are local-only and are excluded from Git. A successful build must report
zero errors and record code/RAM usage plus the generated artifact path. Flashing is a
separate approval-gated step.

## Verified build

The project was fully rebuilt with the installed Keil toolchain on 2026-09-20:

- Target: `Target 1`, device `STM32F103C8`.
- Compiler: ARMCC 5.06 update 5 (build 528).
- Result: 0 errors, 0 warnings.
- Flash usage: 1,404 bytes (`Code=1152`, `RO-data=252`, `RW-data=0`).
- RAM usage: 1,632 bytes (`RW-data=0`, `ZI-data=1632`).
- Local artifacts: `Objects/Project.axf` and `Objects/Project.hex`.
- Corrected PC13 HEX SHA-256:
  `037D3E296EFC4050F3BD5F2B2779A6A3C6F11AF0DF2BE91E71F827BCA5CAF486`.

## Verified download

An earlier PB4 build was downloaded through the installed Keil ST-Link driver on
2026-09-20. Keil reported sector erase complete, programming complete, verification
successful, and application running, but the user observed no board-LED change. That
result invalidated the PB4 board assumption; the PB4 image has been superseded by the
PC13 correction and must not be treated as physically verified firmware.

The download used the project-selected `STM32F103C8` target and
`STM32F10x_128.FLM` algorithm. No Option Bytes, read-protection, mass-erase, or
bootloader operation was requested. The corrected PC13 image has been built successfully
and, after separate user authorization, was downloaded at 15:45:15 on 2026-09-20.
Keil reported sector erase complete, programming complete, verification successful, and
application running. The user then directly confirmed that the on-board PC13 LED was
blinking, completing the physical smoke test.

## RK3568 files kept outside Git

These recovery/build artifacts remain at their original locations and outside Git.
The verified original boot image is retained as the rollback source; the RK3568 boot
partition now contains the UART9 candidate.

| Purpose | Original path | Size (bytes) | SHA256 |
| --- | --- | ---: | --- |
| Verified original boot-partition backup for recovery | `D:\AProject\rk3568-uart9-work\boot-before-uart9.img` | 67,108,864 | `f369d3f0dbc2bcea461f28b82e375dd5d23e7bcce7262e77fd4a47f7cd540b59` |
| UART9 M1 temporary-boot FIT | `D:\AProject\rk3568-uart9-work\safe-build-20260921\boot-uart9-1080p-external.fit` | 37,023,232 | `f239290083095239a400f4954e6a0782b83594a44a60aca8765c3bca7f628d53` |
| Padded 64 MiB UART9 boot image; flashed and read back | `D:\AProject\rk3568-uart9-work\safe-build-20260921\boot-uart9-1080p-external-64MiB.img` | 67,108,864 | `c7e1c1a6d4774529541c83da50b418d25d25353225aa0775a6d67f76aeaef34f` |
| Multi-screen resource image used by candidate FIT | `D:\AProject\rk3568-uart9-work\safe-build-20260921\resource-uart9-1080p.img` | 1,114,112 | `33d962f490f9065496f8ac4aba02175d5fcaea1f571619a83edd3d3f09a35671` |

Pre-write safety gate: the historical `D:\AProject\rk3568-uart9-work\restore-ums-boot.ps1`
expects an older image hash and is preserved unchanged. The candidate-specific
`D:\AProject\rk3568-uart9-work\restore-ums-boot-uart9-candidate.ps1` defaults to
read-only preflight; actual restore requires `-Execute`. Its isolated 64 MiB file
simulation verified candidate-to-original restoration and refused a second write
when the target no longer matched the candidate. An administrator PowerShell
read-only preflight then opened the physical U-Boot UMS device, identified it as
the sole non-system 64 MiB `Linux UMS disk 0`, and measured the unchanged original
boot-image SHA256. The board was returned to Linux, and its boot partition still
matched that original hash. A separate emergency path for an interrupted or
damaged candidate requires `-EmergencyRestore`, the exact observed damaged SHA256,
and confirmation of the current UMS disk number; isolated-file tests verified it
refuses ordinary and wrong-hash restores and recovers with the correct hash. This
does not prove an actual hardware restore after a failed write. The padded candidate
was also rechecked byte-for-byte against the RAM-tested FIT prefix, with only zero
padding after it. The candidate was installed after explicit user approval and
verified by a full boot-partition hash both before and after the warm reboot.
No rollback write has been performed.

## Local acceptance records

These records are deliberately kept out of Git by `local/` or the Keil-output ignore
rules. Their absence from a future clone does not mean the source project is incomplete.

- UART first-round and post-flash serial logs: `local/uart9-diagnostics-20260923/stage1-acceptance-20260923.log` and `stage2-flash-acceptance-20260923.log` (paths relative to repository root).
- Boot write, readback, warm reboot, and physical cold-start record: `local/uart9-diagnostics-20260923/permanent-boot-write-20260923.md`.
- Recovery preflight record: `local/uart9-diagnostics-20260923/ums-preflight-20260923.md`.
- Keil rebuild and ST-Link download logs: `firmware/stm32f103c8t6-uart-link/build-keil-20260923.log` and `flash-keil-20260923.log`.

The versioned firmware source, rollback blink project, `tools/uart-smoke.py`, and
`docs/uart-protocol-draft.md` are the portable project contents. The external boot
images and candidate-specific UMS restore script must remain at the recorded paths
unless separately migrated with their hashes verified.
