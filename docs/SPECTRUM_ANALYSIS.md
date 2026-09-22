# Spectrum Analysis — Gain, Averaging, and the Decimation Noise Floor

Notes from the first real signal-analysis session on KriaBlade (915 MHz ISM noise, then
87.9 MHz FM broadcast), covering three things that weren't obvious at first: picking a sane
gain, why a raw FFT looks worse than it should, and why the in-band noise floor changes with
sample rate. `scripts/analyze_iq.py` bakes in the fixes for all three by default.

## 1. Picking gain: avoid clipping, but don't leave signal on the table

sc16q11 samples are signed 16-bit values, but the usable range is roughly **±2048**
(the ADC's actual resolution). Two failure modes:

- **Too much gain → clipping.** At 30 dB gain on a real FM broadcast station (87.9 MHz),
  I/Q values pinned at the full-scale limit (-2048 to 2047) — visible in the time-domain
  plot as flat-topped spikes.
- **Too little gain → wasted dynamic range.** At 10 dB gain on the same station, peak
  amplitude was only ~382 (≈19% of full scale) — clean, but with headroom to spare.

`scripts/analyze_iq.py` checks for both automatically: a clipping warning when samples sit
near ±2048, and a headroom note when the peak is under ~10% of full scale.

Practical approach: start conservative (10-15 dB for a strong local signal, 30+ dB for weak/
distant sources), capture, check the clipping/headroom notes, and adjust.

## 2. A single raw FFT is noisy — average it (Welch's method)

The first spectrum plots used a single FFT over the whole capture. Technically correct, but
visually deceptive: **every bin has high variance**, so a real, strong, narrowband signal
can look like it's barely poking out of the noise, even when it isn't.

Fix: average many overlapping FFT segments instead of taking one FFT of the whole capture
(this is Welch's method, `scipy.signal.welch`). Same underlying data, dramatically lower
per-bin variance, so the real signal structure becomes visible instead of buried in FFT noise.

`scripts/analyze_iq.py --fft-out spectrum.png` does this by default (`--nperseg` controls the
segment length / averaging trade-off: smaller segments = more averaging = smoother but coarser
frequency resolution).

**Example — the same 87.9 MHz FM capture, before and after:**

| Single raw FFT | Welch-averaged PSD |
|---|---|
| Signal visible but noisy-looking, hard to judge real SNR at a glance | Clean double-hump FM spectral shape, clearly 45 dB above the noise floor, with the peak frequency and SNR annotated |

See `examples/fm_87.9mhz_welch_spectrum.png`.

## 3. The in-band noise floor changes with sample rate (decimation)

At 2 MSPS with a 2 MHz channel filter, the in-band noise floor sat at roughly **-30 dB**, well
above the true out-of-band floor (~-67 dB, from the filter's own stopband rejection). That gap
looked suspicious — like something was wrong with the setup.

Root cause: the bladeRF 2.0 micro's AD9361 RFIC has a native minimum sample rate. 2 MSPS is
below it, so the RFIC engages a **4x hardware decimation filter** to get there (confirmed via
`bladeRF-cli -v debug`, which logs `bladerf2_set_sample_rate: enabling 4x decimation/
interpolation filters` at this rate). That filter stage adds real, measurable
quantization/rounding noise on top of the genuine receiver noise.

**Controlled test** — same antenna, same gain (10 dB), same station (87.9 MHz), only sample
rate changed:

| Sample rate | Decimation | In-band floor |
|---|---|---|
| 2 MSPS | 4x decimation active | ~-30 dB |
| 5 MSPS | none (above native minimum) | ~-42 dB |

**~10 dB difference**, purely from the decimation filter. See
`examples/decimation_noise_floor_comparison.png` for the overlay.

**Nuance:** despite the higher absolute floor, the station's peak stood out *more* from its
own local floor at 2 MSPS than at 5 MSPS — decimation suppresses broadband noise more
aggressively than genuine narrowband signal content, so it's a real trade-off, not simply
"worse."

### Practical takeaway

This is expected AD9361 behavior, not a fault in the setup. Options:

- **For the clearest possible spectrum plot:** capture above ~3 MSPS or so to avoid
  decimation entirely (e.g. the 5 MSPS test above).
- **For low-rate work that has to stay at 2 MSPS or below** (e.g. matching a fixed downstream
  processing rate on the KR260's PL fabric): the elevated floor is just a known
  characteristic to account for, not a bug to chase.

## Reference captures

| File | What it shows |
|---|---|
| `examples/ism_915mhz_clean_capture.png` | Baseline capture after the FPGA fix (docs/FPGA_FIRMWARE_FIX.md) — continuous time-domain noise, no duplicated samples |
| `examples/fm_87.9mhz_welch_spectrum.png` | Clean, averaged spectrum of a real FM broadcast station, with SNR annotated |
| `examples/decimation_noise_floor_comparison.png` | 2 MSPS vs 5 MSPS overlay showing the decimation-induced floor difference |
