# Contributing to AAMS-X

Start with the [README](README.md), [judging guide](docs/JUDGING_GUIDE.md) and [dataset documentation](docs/DATA.md).

## Local checks

```sh
python3 scripts/setup.py
.venv/bin/python -m pytest backend/tests -q
cd frontend
npm ci
npm run build
```

Use a focused branch and pull request. Explain the user-facing change, how to reproduce it and which tests you ran. Include screenshots for interface changes.

## Scientific integrity

- Keep controlled simulation, official synthetic radar and measured solar-radio sources clearly distinguished.
- Policies must only receive observations from their selected receiver window. Never expose hidden truth or future samples to a scheduler.
- Report all preselected seeds, baselines, receiver budgets and confidence intervals. Keep losing results as well as winning results.
- Preserve source units, file hashes, preprocessing parameters and missing-value handling.
- Do not interpret e-CALLISTO as labelled radar-emitter data or claim hardware/field validation.
- Access new TSRD files through the publisher's approved download process. Never commit tokens or credentials.

## Reporting problems

Open an issue with the page, source, seed, receiver settings and reproduction steps. For benchmark issues, attach an exported configuration and experiment ID. Remove private information and credentials from logs.
