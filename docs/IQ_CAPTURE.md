# I/Q Capture Guide

## Quick manual capture (bladeRF-cli one-liner)

```bash
bladeRF-cli -e "set frequency rx 915M; set samplerate rx 2M; set bandwidth rx 2M; \
set agc rx off; set gain rx1 30; \
rx config file=capture1.sc16q11 format=bin n=2000000; rx start; rx wait"
```

This captures 2,000,000 complex I/Q samples (1 second at 2 MSPS) at 915 MHz to
`capture1.sc16q11`. See `docs/SETUP.md` for why `set agc rx off` and the per-channel
`set frequency rx` form are needed, and **before trusting any capture, confirm
`bladeRF-cli -e "version"` shows a matched firmware/FPGA/library set** — see
`docs/FPGA_FIRMWARE_FIX.md` for why a mismatch here can silently corrupt every capture.

### Picking a frequency and gain

- Try `915e6` (ISM band, mostly quiet — good for testing the pipeline) or `87.9e6`-ish
  (FM broadcast — usually strong, good for testing signal detection).
- Start with a conservative gain (10-15 dB for a strong local signal, 30+ dB for a weak/distant
  one) and adjust based on the clipping/headroom notes `scripts/analyze_iq.py` prints — see
  `docs/SPECTRUM_ANALYSIS.md` for the full writeup and a real example of both failure modes.

## Recommended: scripts/capture_iq.py

A parameterized wrapper around the same command sequence:

```bash
python3 scripts/capture_iq.py \
    --freq 915e6 \
    --samplerate 2e6 \
    --bandwidth 2e6 \
    --gain 30 \
    --n 2000000 \
    --out capture1.sc16q11
```

Add `--dry-run` to print the underlying `bladeRF-cli` command without executing it.

## File format

Captures are written as raw binary **sc16q11**: interleaved I, Q samples, each a signed 16-bit
integer (fixed-point, 11 fractional bits — effective range roughly ±2048 with the ADC's actual
resolution). No header.

- File size = `n_samples * 4` bytes (2 bytes I + 2 bytes Q per complex sample).
- Example: 2,000,000 samples → 8,000,000 bytes (~7.7 MiB as reported by `ls -lh`).

## Analyzing a capture

Works entirely headless over SSH — text summary always prints to stdout; a spectrum plot is
optional and saved to a file rather than displayed.

```bash
python3 scripts/analyze_iq.py capture1.sc16q11
```

Example output on a healthy capture:

```
Total complex samples : 2000000
I range               : -149.0 to 149.0
Q range               : -153.0 to 150.0
I mean / Q mean        : -0.562 / -1.172   (near 0 = healthy DC offset)
Magnitude mean / max  : 40.61 / 169.25

Duplicate-run check (repeated I/Q pairs, run >= 5 samples):
  Duplicated fraction : 0.00%
  Max run length      : 3 samples
  OK — no significant duplicated-buffer pattern detected.
```

What to look for:
- **I/Q means near zero** — large nonzero means indicate a DC offset problem.
- **Values well under full scale (~2048)** — values pinned near ±2048 mean clipping; lower the
  gain (`--gain`). A peak under ~10% of full scale triggers a headroom note suggesting you raise
  it instead.
- **Nonzero, varying magnitude** — flat/all-zero data usually means a config or connectivity
  problem, not a "quiet" channel.
- **Duplicate-run check at 0%** — this is the important one. A capture can pass every check
  above while still being badly corrupted; this check catches the specific failure mode
  documented in `docs/FPGA_FIRMWARE_FIX.md` (a stale FPGA image silently duplicating ~75% of
  samples). It runs by default; don't skip it (`--skip-duplicate-check`) unless you have a
  specific reason to.

To also save a spectrum plot as a PNG (an averaged/Welch PSD, not a single noisy raw FFT — see
`docs/SPECTRUM_ANALYSIS.md` for why that matters):

```bash
python3 scripts/analyze_iq.py capture1.sc16q11 --samplerate 2e6 --center-freq 915e6 \
    --fft-out spectrum.png
```

(Requires `matplotlib` and `scipy`; uses matplotlib's non-interactive "Agg" backend so it works
without a display — `pip3 install matplotlib scipy` if not already on the board.)

**Note on sample rate and the noise floor:** at low sample rates (roughly below ~3 MSPS), the
bladeRF's RFIC engages a hardware decimation filter that measurably raises the in-band noise
floor — this is expected behavior, not a fault. See `docs/SPECTRUM_ANALYSIS.md` for the full
explanation and a real before/after comparison.
