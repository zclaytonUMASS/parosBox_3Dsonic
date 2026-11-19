# PCAR 81000: local update and controlled UVW rollout

Updated 2026-11-19. F2 and F3 have received the driver and 789AB5 format after user authorization. F1 is deferred; Colorado is excluded. No GitHub fetch/push was performed by the assistant. Obtain authorization before adding stations to deployment scope; opening a configuration menu pauses measurements.

## Driver and column definitions

The driver accepts both existing `789AB` and new `789AB5` complete CR-terminated records. This permits installing the driver before changing the instrument and returning to the old output without reverting code. It does not send configuration commands or set the sample rate. `LEGACY_COLUMNS` and `UVW_COLUMNS` in the driver define wire order:

| Position | Custom selector | InfluxDB field | PCAR units |
|---|---|---|---|
| 1 | 7 | speed_3d | m/s |
| 2 | 8 | azimuth | degrees |
| 3 | 9 | elevation | degrees |
| 4 | A | speed_of_sound | m/s |
| 5 | B | sonic_temperature | Celsius |
| 6 | 5, first value | u | m/s |
| 7 | 5, second value | v | m/s |
| 8 | 5, third value | w | m/s |

Old records have no u/v/w fields; they are not zero-filled. The writer stores named InfluxDB fields, not positional CSV columns. `processor.py` forwards complete line-protocol records and needs no column change. Existing five-field queries continue working; export/dashboard queries must explicitly include u/v/w when desired. Historical files remain unchanged. The parser cannot distinguish a different eight-field custom ordering; verify the instrument report before relying on labels.

Malformed widths, nonnumeric/nonfinite values and incomplete records are rejected. Existing exit-after-11-consecutive-failures behavior remains. Finite values are not proof of acoustic validity: requested formats contain no error-code field. Preserve existing error handling; adding E would be a separate schema change.

## Manufacturer documentation and firmware gate

Sources: [81000 manual, revision I](https://www.youngusa.com/wp-content/uploads/2008/01/81000-9028I29.pdf), sections 4, 6.5, 6.7 and Appendix A; [81000VRE manual](https://www.youngusa.com/wp-content/uploads/2021/03/81000VRE-90H.pdf), sections 4–7 (corroborating family reference, not a substitute for identifying the deployed model).

Documented menu path: three rapid ESC characters (ASCII 27), R to report, S for setup, S for serial-output format, 1 for CUSTOM, then `789AB5` and Enter at the custom-string prompt. Follow displayed menus back to the main menu, R to verify, then X to operate. In setup, O opens output-rate choices; F selects 20 Hz in these manuals. Leave an existing 20 Hz setting alone. Selector 5 emits all three components. Parameters persist in nonvolatile memory.

Earlier chat reports firmware 6.6.13, 7.0.01 and 6.8.01, but does not establish which station has which firmware. These are historical reports, not live verification. If displayed menus differ, stop and record them; do not paste a blind command sequence. Live F2/F3 sessions confirmed that multi-character input must be paced (200 ms between characters worked), while the ESC triplet stays rapid. Reports have multiple PRESS ANY KEY pages: advance every page and wait for the main command menu before exiting. Normalize whitespace in menu labels, including tabs. Compare all report settings before/after, excluding the deliberately changed format line and its expected EEPROM checksum change.

With the documented orientation, +u is wind from east, +v from north, and +w an updraft. Record actual mounting orientation before interpreting these as geographic components. Retain 38400 baud, 8N1, no flow control, m/s, and existing averaging/calibration settings. Verify 20 Hz and averaging 0 in the final report.

## Deployment scope and station inventory

| Station | SSH target/user | Sensor ID / service | Serial by-id path | RX wiring / firmware | Approved / verified |
|---|---|---|---|---|---|
| F2 | parosf2 / pi | 81000 / paros-sampler-81000 | FTDI BH00OG3U | RX verified by menu; 7.0.01 | 789AB5 applied 2026-11-19 |
| F3 | parosf3 / pi | 81000 / paros-sampler-81000 | FTDI BH00FBK5 | RX verified by menu; 6.8.01 | 789AB5 applied 2026-11-19 |
| C1 | excluded | no change | no change | no configuration session | no deployment |
| C2 | excluded | no change | no change | no configuration session | no deployment |
| C3 | excluded | no change | no change | no configuration session | no deployment |

Do not substitute the sample paros2.json configuration. The repository generates `paros-sampler-<sensor_id>.service`; that is a naming convention, not confirmation of deployed names. Do not run setup.sh or recreate all station services for this change.

After agreeing on an SSH target, inspect without stopping services:

```sh
hostname
systemctl list-units --type=service --all 'paros-sampler-*'
ls -l /dev/serial/by-id/
```

For the candidate sonic service, inspect `systemctl cat ACTUAL_SERVICE` and `systemctl show ACTUAL_SERVICE -p ExecStart -p WorkingDirectory -p User -p Restart`. Confirm ExecStart uses Young_81000.py, its sensor ID, Python interpreter, repository directory and exact device argument. Read that host's sensor JSON and resolve the by-id path with `readlink -f`. Use `sudo fuser -v ACTUAL_DEVICE` to identify the owner; do not read the serial stream alongside the sampler. Identify data location from the deployment configuration without sharing credentials. Record baseline record counts, latest timestamps, service restart count and uploader health.

For remote control, verify the USB adapter TX reaches the sensor RX, sensor TX reaches adapter RX, and signal ground is connected. Receiving measurements proves only the sensor-to-Pi direction. Use an RS-232 level adapter, not bare Pi GPIO TTL. For a standard PC-style DB9 adapter, pin 3 is TX, pin 2 RX and pin 5 ground; verify the actual adapter documentation/pinout and sensor terminal labels. A local wiring record/photo or successful menu response is needed. Full-duplex, non-bussed RS-485 needs its appropriate wiring instead. If RX is unwired, software cannot repair it remotely.

## One station at a time, after approval

Current scope: F2 and F3, with F1 deferred until it is accessible. Colorado C1/C2/C3 are excluded by the user. Continue only after each station passes; never use a fleet-wide loop.

1. Record the actual service, device, interpreter, code path, data path and SSH target. Preserve current driver with a dated backup and SHA-256 checksum. Save service definition, sensor config and baseline health. Stage the new driver under a temporary name in the same directory. Check syntax with the service's Python, then compare checksums with the laptop file. Have an independent SSH session available.
2. Stop ONLY the identified sonic sampler with `sudo systemctl stop ACTUAL_SERVICE`. Verify inactive and confirm no process holds its serial device. Pressure and uploader services stay running. Do not use a generic kill command.
3. Replace only Young_81000.py with the staged file, retaining ownership and permissions. Start the sampler and verify it records the original five fields normally. This proves the software upgrade works before touching instrument settings.
4. Stop that sampler again and verify exclusive serial access. Use an already available terminal, for example `picocom --baud 38400 --flow n --databits 8 --parity n --stopbits 1 ACTUAL_BY_ID_PATH`. If no terminal is available, arrange installation before the outage. Do not assume /dev/ttyUSB0 is the sonic.
5. Confirm existing streaming data, then enter the menu and save the complete R report (firmware and all settings). Apply only the custom-format change using the documented, displayed menus above. Compare before/after reports: format changes to 789AB5; rate remains 20 Hz and other settings remain unchanged. Exit to operating mode and confirm eight numeric values. Quit picocom (Ctrl-A, then Ctrl-X) so it releases the port.
6. Start ONLY that sonic service. Check active state and `journalctl -u ACTUAL_SERVICE --since '5 minutes ago' --no-pager`. Confirm fresh local records include all eight named fields and the correct sensor tag. Check uploaded records too; old queued data is not evidence of new-format success.
7. Observe for at least five minutes: roughly 6,000 fresh samples at 20 Hz, stable service restart count, no repeated parse failures, no growing uploader backlog. Compute count / elapsed time over a continuous window, inspect gaps and compare with baseline. Pi receipt timestamps can have jitter; serial arrival times alone are not precision acquisition timestamps. If invalid data is omitted by the existing sensor setting, investigate missing output rather than assuming a rate change.
8. Record UTC change time, reports, checksums, sample lines, counts and acceptance result before requesting approval for the next station.

At 38400 baud with 8N1, the theoretical line budget at 20 Hz is 192 bytes per record (including terminators). Verify measured line length is comfortably below that and check sustained cadence; configuration alone is not proof of achieved rate.

## Rollback

If the software-only stage fails, stop the sonic service, restore its saved driver, restart and verify original logging; the sensor still has its old format.

If eight-field operation fails, stop the sonic sampler, take exclusive terminal access, restore the exact saved custom string (expected 789AB), verify the saved rate/settings with R, exit to operating mode, close the terminal, then restart. The new driver can remain in place and log five-field data. To restore old code too, restore sensor output FIRST: old code rejects eight fields. Never leave the instrument in its menu. If terminal access is lost, regain the connection and inspect state rather than power-cycling blindly. Verify resumed timestamps and uploader health; document the outage. Do not proceed to another station until recovery is complete.

## Tests and GitHub steps (run by the user)

Use Python 3.11+ with pyserial, influxdb-client and python-dotenv (existing runtime requirements). From the prepared checkout:

```sh
python -m unittest discover -s tests -p 'test_young_81000.py' -v
git status --short --branch
git diff --check
git diff -- paros_sensors/Young_81000.py
git remote -v
```

The prepared checkout is `work/met5-driver-only` under the PCAR project mirror, branch `add-met5-driver-only`, local base `31a4f9d`. Its `myfork` remote points to zclaytonUMASS/parosBox_3Dsonic. Remote state and PR number have not been checked. When ready to connect yourself:

```sh
git fetch myfork add-met5-driver-only
git log --oneline HEAD..myfork/add-met5-driver-only
```

If the remote has new commits, reconcile them before proceeding; do not force-push. If the branch is still based on the same remote history:

```sh
git add paros_sensors/Young_81000.py tests/test_young_81000.py docs/young_81000_uvw_rollout.md
git commit -m "Support RM Young 81000 UVW custom output"
git push myfork HEAD:add-met5-driver-only
```

An existing PR using that head branch receives the commit automatically. Inspect its full diff, including the prior MET5 work, and add the UVW behavior and test results to its description without removing the MET5 explanation. If that PR is already merged/closed, open a separate branch/PR instead. No PR is merged as part of this procedure. Deployment remains a separate approved action.
