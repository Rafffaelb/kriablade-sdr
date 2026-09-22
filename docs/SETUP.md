# KR260 + bladeRF Setup Guide

Steps to go from a fresh SSH session on the KR260 to a working, passwordless bladeRF connection.

## 1. Access the board

```bash
ssh ubuntu@kria-kr260
```

Confirmed environment: Ubuntu 22.04.4 LTS, kernel `5.15.0-1027-xilinx-zynqmp`, aarch64.

## 2. Verify Python

```bash
python3 --version   # Python 3.10.12
```

## 3. Confirm USB connectivity

```bash
lsusb        # look for "Nuand LLC bladeRF 2.0 micro" (VID:PID 2cf0:5250)
lsusb -t     # confirm negotiated speed is 5000M (USB 3.0), not 480M
```

The bladeRF should appear on one of the `xhci-hcd` (USB 3.0) root hubs, not a `480M` (USB 2.0)
one — that matters for sustaining 61.44 MSPS streaming later.

## 4. Confirm bladeRF tools are installed

```bash
which bladeRF-cli
bladeRF-cli --version
```

On this image the tools come from apt:

```bash
dpkg -l | grep -i bladerf
```

```
bladerf                0.2021.10-2   arm64
bladerf-firmware-fx3    0.2021.10-2   all
bladerf-fpga-hostedxa4  0.2021.10-2   all
bladerf-fpga-hostedxa9  0.2021.10-2   all
libbladerf-dev          0.2021.10-2   arm64
libbladerf2             0.2021.10-2   arm64
python3-bladerf         0.2021.10-2   arm64
```

Check whether apt has anything newer:

```bash
sudo apt update
apt-cache policy bladerf libbladerf2
```

If `Installed:` and `Candidate:` match, apt is already at the latest packaged version — going
further requires building from Nuand's GitHub source, which is generally not necessary unless you
hit a bug specifically tied to firmware/library version skew.

## 5. Fix USB permissions (use bladeRF-cli without sudo)

By default the USB device node (e.g. `/dev/bus/usb/002/004`) is owned `root:root` with no group
access, so `bladeRF-cli -p` as a normal user fails with:

```
Found a bladeRF via VID/PID, but could not open it due to insufficient permissions,
or because the device is already open.
```

Fix: install the udev rule in `udev/88-nuand-bladerf.rules`:

```bash
sudo cp udev/88-nuand-bladerf.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Your user needs to be in the `plugdev` group (check with `groups`; it is by default on this
image). Then verify, no `sudo` needed:

```bash
bladeRF-cli -p
bladeRF-cli -e "version"
```

## 6. Known notes / gotchas

- **Firmware/library version warning:** firmware `v2.6.0` is newer than libbladeRF `2.4.1`'s
  compatibility table. This is an informational warning only — everything tested so far
  (`-p`, `version`, RX capture) works fine.
- **FPGA "configured by USB host":** the bladeRF 2.0 micro's own Cyclone V FPGA image loads fresh
  over USB each time it connects — this is normal bladeRF behavior and is unrelated to the KR260's
  own Zynq UltraScale+ PL fabric.
- **`set frequency <value>` is deprecated** in favor of per-channel `set frequency rx <value>` /
  `set frequency tx <value>`.
- **AGC is enabled by default** on RX. `set gain <channel> <value>` fails with
  `Operation invalid in current state` until you run `set agc <rx|tx> off` first. (There is no
  `gain_mode` keyword in bladeRF-cli 1.8.0 — use `set agc`.)
- **"Overall gain" isn't 1:1 with your requested value.** bladeRF 2.0's reported "RX1 overall"
  gain reflects combined internal gain stages (RFIC LNA + mixer), so after
  `set gain rx1 30` the tool may report a different overall dB figure — that's expected.
