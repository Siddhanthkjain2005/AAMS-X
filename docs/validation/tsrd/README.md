# Official TSRD evaluation

SIH problem statement 26055 specifies the Alan Turing Institute radar dataset hosted on Hugging Face. This project uses the installed official synthetic validation recording `tsrd_val_stare_config_0.h5`, not generated data under an official badge.

648,034 retained PDWs, no pulse truncation. Source SHA-256: `d25a4189f287ca044f46718baea7471eb1f9ab766b7715c738bb8edf8ac1e474`.

Executed: 24 paired worlds and 192 policy evaluations. All eight algorithms use the same immutable source/noise world within each seed and the same receiver budget. Seeds 42–47, 64 frequency bands, 240 evaluated time slots. Native source time/frequency coordinates determine the effective receiver geometry. Four instantaneous bandwidth budgets:

| Budget | Fixed sweep recall | MAG-NTS recall | Thompson recall |
|---|---:|---:|---:|
| 2 / 64 bands | 2.71% | 13.27% | 15.83% |
| 4 / 64 bands | 5.47% | 31.48% | 36.75% |
| 8 / 64 bands | 11.07% | 37.38% | 39.55% |
| 16 / 64 bands | 21.96% | 52.34% | 55.30% |

Values are means across six seeds. MAG-NTS beats fixed sweep here, but Thompson performs better on this recording. Do not claim universal superiority. Full statistics, Student-t confidence intervals, paired differences and all ablations are in `report.json` and `width-*.json`. Per-seed measurements are in `width-*.csv`. Every saved replay passed registry and trace checksum validation.

Limitations: one synthetic validation recording, not independent radar recordings per seed. Seeds vary modeled noise and policy randomness. Receiver energy is simulated over the official pulse occupancy, not measured IQ data. Recall counts recovered occupied time-frequency cells, not individual pulse deinterleaving accuracy. Conditional interception delay excludes never-intercepted episodes. The official publisher's deinterleaving benchmark uses different metrics; these are AAMS-X scheduling evaluations.

Reproduce from the project root:

```sh
PYTHONPATH=. .venv/bin/python scripts/validate_official_tsrd.py
.venv/bin/python -m pytest backend/tests -q
```

Publisher: https://huggingface.co/datasets/alan-turing-institute/turing-synthetic-radar-dataset
