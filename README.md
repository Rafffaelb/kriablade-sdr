# KriaBlade

A heterogeneous SDR platform pairing a **bladeRF 2.0 micro** (RF frontend) with an
**AMD Kria KR260** (Zynq UltraScale+ MPSoC digital backend).

- **Frontend (bladeRF 2.0 micro):** RF tuning (47 MHz – 6 GHz), pre-filtering, hardware I/Q capture.
- **Backend (Kria KR260):** PL (FPGA fabric) for DSP acceleration, quad-core Cortex-A53 for
  control-plane Linux, dual Cortex-R5F for hard real-time tasks, 10GbE SFP+ for network offload.

See `docs/ENGINEERING_RATIONALE.txt` and `docs/JOURNAL_MAPPING.txt` for the full architecture
rationale and target-publication mapping.

## Repository layout

```
KriaBlade/
├── README.md                       - this file
├── docs/
│   ├── ENGINEERING_RATIONALE.txt   - why this architecture (existing)
│   ├── JOURNAL_MAPPING.txt         - publication venue mapping (existing)
│   ├── SETUP.md                    - board access, bladeRF connectivity, udev fix
│   ├── IQ_CAPTURE.md               - how to run and analyze an I/Q capture
│   ├── FPGA_FIRMWARE_FIX.md        - root-cause writeup: corrupted captures fixed by
│   │                                  rebuilding libbladeRF + reflashing the FPGA image
│   └── SPECTRUM_ANALYSIS.md        - gain selection, averaged (Welch) spectra, and the
│                                      sample-rate-dependent decimation noise floor
├── examples/
│   ├── ism_915mhz_clean_capture.png          - baseline capture after the FPGA fix
│   ├── fm_87.9mhz_welch_spectrum.png         - clean averaged spectrum of a real FM station
│   └── decimation_noise_floor_comparison.png - 2 MSPS vs 5 MSPS noise floor overlay
├── scripts/
│   ├── capture_iq.py               - parameterized capture wrapper (bladeRF-cli)
│   └── analyze_iq.py               - load/summarize/plot a capture file (duplicate-run
│                                      check + Welch spectrum + clipping/headroom checks,
│                                      all on by default)
├── udev/
│   └── 88-nuand-bladerf.rules      - lets the bladeRF be used without sudo
└── .gitignore
```

## Quickstart

```bash
# 1. Access the board
ssh ubuntu@kria-kr260

# 2. One-time: install the udev rule so bladeRF-cli works without sudo
sudo cp udev/88-nuand-bladerf.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3. Confirm the bladeRF is visible
bladeRF-cli -p
bladeRF-cli -e "version"

# 4. Capture some I/Q samples (try 915e6 for ISM/quiet, or 87.9e6-ish for FM broadcast)
python3 scripts/capture_iq.py --freq 915e6 --samplerate 2e6 --gain 30 \
    --n 2000000 --out capture1.sc16q11

# 5. Sanity-check the capture (works headless over SSH) — checks for clipping,
#    headroom, and the duplicate-sample corruption from docs/FPGA_FIRMWARE_FIX.md
python3 scripts/analyze_iq.py capture1.sc16q11 --samplerate 2e6

# 6. Optional: save an averaged (Welch) spectrum plot — see docs/SPECTRUM_ANALYSIS.md
python3 scripts/analyze_iq.py capture1.sc16q11 --samplerate 2e6 --center-freq 915e6 \
    --fft-out spectrum.png
```

## Hardware / environment

- **KR260:** hostname `kria-kr260`, Ubuntu 22.04.4 LTS, kernel `5.15.0-1027-xilinx-zynqmp`, aarch64.
- **bladeRF 2.0 micro:** VID:PID `2cf0:5250`, connects on a USB 3.0 SuperSpeed port (verified via
  `lsusb -t`, negotiated at 5000M).
- **bladeRF host tools:** built from Nuand's GitHub source (`bladeRF-cli` 1.10.0, libbladeRF
  2.6.1) — **not** the apt package. The apt `jammy` package is capped at `0.2021.10-2`
  (libbladeRF 2.4.1), which is too old to catch a firmware/FPGA version mismatch that silently
  corrupted early captures. See `docs/FPGA_FIRMWARE_FIX.md` for the full story — **read this
  before trusting a capture from a freshly-imaged board.**
- **FPGA:** flashed to v0.16.0 (xA4 variant), matched to firmware v2.6.0.

## Status

- [x] SSH access to KR260 confirmed
- [x] Python 3 verified on-board (3.10.12)
- [x] bladeRF USB 3.0 connectivity confirmed
- [x] bladeRF-cli / libbladeRF working without sudo (udev rule installed)
- [x] libbladeRF/bladeRF-cli built from source, FPGA updated to v0.16.0 (fixes corrupted
      captures — see `docs/FPGA_FIRMWARE_FIX.md`)
- [x] Clean I/Q capture + sanity analysis confirmed (915 MHz, 2 MSPS, 0% duplicated samples)
- [x] Real signal validated end-to-end: 87.9 MHz FM broadcast station captured, clipping/gain
      trade-off characterized, averaged (Welch) spectrum confirms ~45 dB SNR — see
      `docs/SPECTRUM_ANALYSIS.md`
- [x] Sample-rate-dependent decimation noise floor characterized (2 vs 5 MSPS, ~10 dB
      difference, expected AD9361 behavior) — see `docs/SPECTRUM_ANALYSIS.md`
- [ ] FPGA / PL DSP pipeline — not started yet
