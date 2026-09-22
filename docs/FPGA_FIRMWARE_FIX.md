# FPGA/Firmware Version Mismatch — Root-Cause Writeup

## Symptom

The very first I/Q captures (915 MHz, 2 MSPS, bladeRF 2.0 micro → KR260) looked plausible at a
glance but were badly corrupted: **~75% of every capture's samples were stuck in repeated blocks
of exactly 1,536 samples**, with a new "held" I/Q value roughly every 1,536 samples throughout the
entire file. This was invisible in a coarse sanity check (means near zero, values in range) and
only showed up when checking for literal repeated (I, Q) pairs.

## What did *not* fix it (ruled out, in order)

1. **Host-side USB buffering** (`buffers=`, `samples=`, `xfers=`, `timeout=` on `rx config`) —
   no change.
2. **Storage speed** (writing to `/dev/shm` RAM disk instead of the home directory/SD-backed
   filesystem) — no change.
3. **Sample rate** — identical artifact (same 1,536-sample max run length) at both 2 MSPS and
   10 MSPS, ruling out an RFIC decimation-filter theory (2 MSPS requires the AD9361's 4x
   decimation filter; 10 MSPS does not).

The fact that the exact same 1,536-sample run length showed up regardless of sample rate, file
length, or storage target was the key clue: it pointed to something fixed and structural in the
streaming pipeline, not something tunable from `bladeRF-cli`.

## Root cause

The board was running:
- Firmware: **v2.6.0**
- FPGA: **v0.14.0** (loaded fresh over USB at every connect — normal for the bladeRF 2.0 micro)
- libbladeRF (apt/`jammy` package): **2.4.1** — the latest available via `apt`, but old enough
  that it does not enforce a firmware/FPGA compatibility check.

Firmware v2.6.0 actually **requires FPGA v0.16.0 or later**. The apt-packaged libbladeRF (2.4.1)
silently tolerated this mismatch and opened the device anyway, streaming corrupted data (the
1,536-sample repeat pattern) without ever reporting an error.

Building the latest libbladeRF/bladeRF-cli from source immediately surfaced the real error that
the old library was swallowing:

```
FPGA v0.14.0 was detected. Firmware v2.6.0 requires FPGA v0.16.0 or later.
Please load a different FPGA version before continuing.
```

Additionally, the `.rbf` FPGA bitstream files already present on the system at
`/usr/share/Nuand/bladeRF/*.rbf` (from the `bladerf-fpga-hostedxa4`/`hostedxa9` apt packages) were
themselves stale v0.14.0 images, not the v0.16.0 that ships with current Nuand releases.

## Fix

### 1. Build libbladeRF / bladeRF-cli from source

The apt/`jammy` package is capped at `0.2021.10-2` (libbladeRF 2.4.1) — no `apt upgrade` will move
past this. Build from Nuand's GitHub source instead:

```bash
sudo apt install -y build-essential cmake git libusb-1.0-0-dev pkg-config \
    libncurses-dev libedit-dev libcurl4-openssl-dev

cd ~
git clone https://github.com/Nuand/bladeRF.git
cd bladeRF
mkdir -p host/build && cd host/build
cmake ..
make -j$(nproc)
sudo make install
sudo ldconfig
```

**Remove the old apt packages** — leaving both installed causes the new `bladeRF-cli` binary to
dynamically link against the *old* `libbladerf2` shared library, producing
`symbol lookup error: bladeRF-cli: undefined symbol: bladerf_get_feature`:

```bash
sudo apt remove --purge -y bladerf libbladerf2 libbladerf-dev python3-bladerf
sudo ldconfig
hash -r    # clear bash's cached path to the old /usr/bin/bladeRF-cli
```

Verify:
```bash
which bladeRF-cli        # should be /usr/local/bin/bladeRF-cli
bladeRF-cli --version    # should show the git-built version, e.g. 1.10.0-git-<hash>
```

### 2. Update and flash the FPGA image

The build includes `bladeRF-update`, Nuand's official updater:

```bash
bladeRF-update -y --rm -v
```

**Note:** when run with `sudo`, downloaded files land in `/root/.config/Nuand/bladeRF/`, not the
system-wide `/usr/share/Nuand/bladeRF/` that `bladeRF-cli` actually checks regardless of which
user runs it. Copy the verified files into the system path explicitly:

```bash
sudo cp /root/.config/Nuand/bladeRF/hostedxA4.rbf /usr/share/Nuand/bladeRF/hostedxA4.rbf
sudo cp /root/.config/Nuand/bladeRF/hostedxA9.rbf /usr/share/Nuand/bladeRF/hostedxA9.rbf
sudo cp /root/.config/Nuand/bladeRF/hostedxA5.rbf /usr/share/Nuand/bladeRF/hostedxA5.rbf
sudo cp /root/.config/Nuand/bladeRF/hostedx40.rbf /usr/share/Nuand/bladeRF/hostedx40.rbf
sudo cp /root/.config/Nuand/bladeRF/hostedx115.rbf /usr/share/Nuand/bladeRF/hostedx115.rbf
```

Updating the files on disk does **not** push a new image to the device by itself — the FPGA
already loaded into the device's volatile memory from a previous connect is still the old one.
`bladeRF-cli`'s normal open path also can't help here, since it aborts *before* any interactive
command (including `load fpga`) can run, due to the very version check we're trying to fix. Use
the dedicated command-line flag instead, which loads the image before that check:

```bash
# Confirm the correct board variant — this device is an xA4 (smaller Cyclone V).
# Loading the wrong variant fails fast with a file-size mismatch error, so it's safe to try:
bladeRF-cli -l /usr/share/Nuand/bladeRF/hostedxA4.rbf -e "version"
```

Once that succeeds (reports `FPGA version: 0.16.0`), make it permanent by flashing it to the
board's own SPI flash, so it autoloads on every future connect without needing `-l`:

```bash
sudo bladeRF-cli -L /usr/share/Nuand/bladeRF/hostedxA4.rbf
```

Verify — the FPGA version should no longer say "(configured by USB host)", confirming it's now
autoloading from onboard flash:
```bash
bladeRF-cli -e "version"
```

## Confirming the fix

Re-ran the same 2,000,000-sample capture at 915 MHz / 2 MSPS and checked for duplicate-run
artifacts (see `scripts/analyze_iq.py`, which now includes this check by default):

| | Before fix | After fix |
|---|---|---|
| Duplicated samples (≥5-sample run) | ~75% | **0%** |
| Max repeat-run length | 1,536 samples | 1 sample |
| FPGA version | 0.14.0 | 0.16.0 |
| libbladeRF | 2.4.1 (apt) | 2.6.1 (source) |

## Takeaway for future setup on a new/reflashed KR260

If you re-image the KR260 or set this up on a new board, **do not rely on the apt-packaged
bladeRF tools** — go straight to the source build in step 1, and check `bladeRF-cli -e "version"`
reports matching firmware/FPGA versions before trusting any capture from that device. The old
library gave no warning that the data was corrupted; only an explicit duplicate-run check (or a
newer library that enforces the version check) caught it.
