# AAMS-X documentation hub

This directory documents the code that is currently in this repository. Start here if
you are new to AAMS-X or if an AI coding agent needs to change it safely.

## What the project is, in plain words

AAMS-X is a research application for deciding **which small part of a frequency band to
observe next** when a receiver cannot watch the whole band at once.

It does not control a physical radio. It replays previously recorded, public
e-CALLISTO measurements from disk. During an experiment, a scheduling algorithm chooses
one contiguous group of regions. Only that group is revealed to the algorithm. A separate
evaluation layer can see the complete recorded band and uses it to score the choice. This
separation is essential: the complete band is an evaluation reference, not information the
algorithm was allowed to use when deciding.

The application has three ways to use the same core:

- a React browser console for launching and inspecting runs;
- a FastAPI REST and WebSocket service used by that console;
- an `aamsx` command-line interface and research scripts for repeatable experiments.

## Where to start

| If you want to… | Read this first |
|---|---|
| Understand the whole product | [Developer guide](DEVELOPER_GUIDE.md) |
| Follow one decision from data to result | [Runtime and data](RUNTIME_AND_DATA.md) |
| Work on the browser interface | [Frontend guide](FRONTEND.md) |
| Call or change an endpoint | [API reference](API.md) |
| Run locally, use Docker, or deploy | [Operations and deployment](OPERATIONS.md) |
| See tests, risks, security gaps, or stale claims | [Quality and risk register](QUALITY_AND_RISKS.md) |
| Study the scheduling mathematics | [Algorithms](ALGORITHMS.md) |
| Audit data origin and calibration | [Data](DATA.md) |
| Review measured research results | [Experiments](EXPERIMENTS.md) |
| Present the project | [SIH demo walkthrough](SIH_DEMO.md) |
| Understand known scientific limitations | [Limitations](LIMITATIONS.md) |

## The shortest useful reading path

1. Read the first two sections of [Developer guide](DEVELOPER_GUIDE.md).
2. Read “One episode, end to end” in [Runtime and data](RUNTIME_AND_DATA.md).
3. Pick the relevant change playbook in the developer guide.
4. Check [Quality and risk register](QUALITY_AND_RISKS.md) before relying on a comment,
   feature flag, deployment assumption, or test-count claim.

## Documentation boundaries

The documents have deliberately different jobs:

- `DEVELOPER_GUIDE.md`, `RUNTIME_AND_DATA.md`, `FRONTEND.md`, `OPERATIONS.md`, and
  `QUALITY_AND_RISKS.md` describe the current implementation and maintenance workflow.
- `API.md` describes the current HTTP and WebSocket contract.
- `ALGORITHMS.md`, `DATA.md`, and `EXPERIMENTS.md` are the scientific record. The
  published values in `EXPERIMENTS.md` are checked against the stored JSON artefacts by
  `scripts/verify_docs.py`.
- `SIH_DEMO.md` is presentation material, not an operational runbook.
- `LIMITATIONS.md` discusses scientific and engineering limitations, while
  `QUALITY_AND_RISKS.md` is the code-audit source of truth when the two disagree.

## Source-of-truth order

When two sources disagree, use this order:

1. executable code and validation models;
2. automated tests that currently run;
3. generated artefacts such as OpenAPI and benchmark JSON;
4. these implementation documents;
5. comments, older research prose, and presentation material.

Important qualifications:

- The current directory does not contain Git metadata, so commit history and ownership
  cannot be inferred here.
- A configuration field is not proof that behavior is enforced. Unused and partially
  wired settings are listed in the risk register.
- “Replay” has two meanings in the UI. Real Spectrum Replay reads cached measurements;
  Replay Experiment re-executes a stored experiment configuration.
- “Truth” in code means the occupancy reference derived from the recorded measurement and
  configured threshold. It is not independently labelled emitter ground truth.

## Keeping the docs correct

For every behavior change:

1. update code and tests;
2. update the relevant implementation document and `API.md` if the wire contract moved;
3. update `ALGORITHMS.md` or `DATA.md` if a scientific assumption moved;
4. regenerate benchmark artefacts before editing a measured number;
5. run `make verify-docs`, never hand-adjust a result to make the checker pass;
6. update `QUALITY_AND_RISKS.md` when a listed discrepancy is fixed or a new one is found.

The [new-feature checklist](DEVELOPER_GUIDE.md#new-feature-checklist) gives the complete
cross-layer version of this process.
