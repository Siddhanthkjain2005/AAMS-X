# AAMS-X — three-minute judging sequence

## Before the session

1. Complete dependency setup while internet is available: `python3 scripts/setup.py`.
2. Run `./run_tests.sh` and the browser checks described in the README.
3. Launch `./start_demo.sh`; open `http://127.0.0.1:8000`.
4. Open Data Provenance and verify the measured e-CALLISTO artifact is available.
5. If TSRD access has been approved, import an authorized **stare-mode** HDF5 and refresh the catalog. Otherwise explicitly state that the tested importer is ready but official pulses are not installed.
6. Confirm the recorded sudden, periodic and agile demos and the multi-seed benchmark appear in replay/history. These are real saved experiments, not a simulated live stream.

The default demo uses seed 42. Do not modify the world in response to algorithm performance. Both receivers share the same immutable world and random detector fields.

## 0:00–0:20 — explain the constraint

Open **Command Center**. Use the spectrum illustration and the `4 / 48` bandwidth card:

> “We can monitor a wide spectrum, but this receiver can listen to only four bands at a time. A fixed sweep follows a schedule. AAMS-X asks where the next observation has the highest expected value.”

The illustration is labelled a concept diagram. It contains no experiment results.

## 0:20–0:40 — show the boundary and one decision

Open **Architecture** and click **TRACE ONE DECISION**. Follow the highlighted observation through the blocks. Click **Inspect the ten-step decision** if asked for the exact numbers.

Show the frozen Observation contract. The simulator/evaluator owns truth; the policy receives only energy and HIT/MISS values in its selected contiguous window.

## 0:40–1:30 — run the fair duel

Open **Live Duel**, choose **Sudden Appearance**, seed **42**, horizon **360**, width **4 / 48**, and click **RUN FAIR DUEL**.

- Start with Ground Truth **off**: only observations appear.
- Point to the shared environment fingerprint and fairness indicators.
- Watch fixed sweep's repeated path and the adaptive receiver's changing allocation.
- Enable **Ground truth** to enter **EVALUATION / JUDGE VIEW** and reveal missed activity.
- Read global interception share, conditional detector Pd, delay, retunes and reward/cost distinctly.

At 1× the presentation pacing is approximately ten slots/second. 2× and 4× change presentation/computation pacing, not the scientific time grid or sensing budget.

## 1:30–1:55 — explain the action

Click **Trace one decision** to freeze. Inspect probability, uncertainty, memory/periodicity evidence and candidate score contributions. Compare the selected window to a rejected alternative.

> “This band may be worth observing because activity is likely, because our evidence is stale, or because the information gain is high. Those are different reasons, and the interface shows their actual contributions.”

Continue, or open **AI Observability** to inspect memory matches and observed CUSUM change events.

## 1:55–2:15 — periodic challenge

Use **REPLAY**, select `periodic · 420 slots · seed 42`, and scrub forward. The recording label remains visible.

The bundled run learns an 18-slot period in bands 12/13. Show the event timestamps and confidence. With Judge View enabled, compare prospective forecasts to actual next onsets and their errors. Wrong or tentative candidates are intentionally retained.

Alternatively press **START PERIODIC CHALLENGE** to learn from a fresh cold start; use 4× if time is short.

## 2:15–2:35 — show genuine public data

Open **Data Provenance** and **Dataset Explorer**. Show:

- Official synthetic radar source and authorized-import status.
- The measured e-CALLISTO station, 2024 timestamp, original FITS, standardized sample count and checksums.
- The distinction between simulation truth and an unlabelled measured recording.

Click **RUN RECEIVER REPLAY** on the measured file. Explain that truth-dependent EW metrics are N/A, while the same observation-only scheduler can prioritize measured energy regions.

## 2:35–2:50 — benchmark and ablation evidence

Open **Benchmark Lab** and select the bundled 30-world report. Inspect several scenarios and the no-memory/no-information/no-change rows.

> “MAG-NTS helps under suitable dynamics. Vanilla Thompson can be stronger in stable conditions. We expose both outcomes across the same seeds, with variance and uncertainty.”

All benchmark worlds have a working Replay Run link and downloadable CSV/JSON. For a quick live benchmark, choose one scenario, one seed and 24–96 slots.

## 2:50–3:00 — finish with reproducibility

Open the cube if a spatial explanation is useful, or return to Architecture:

> “Instead of scanning every band equally, AAMS-X learns where a limited sensing budget is most valuable. The experiment ID, seed, dataset, receiver configuration and complete trace make that claim inspectable.”

End with an export or replay, not a hardcoded winner badge.

## Offline fallback

After setup, no remote API is needed. If running another experiment is inconvenient, use the included recordings. The same visuals and decisions are replayed, explicitly labelled **Recorded reproducible experiment replay**.

If WebGL is unavailable, use the 2D waterfall and belief views. If a public source is not installed, the catalog reports its status and the controlled simulator remains usable. Do not describe simulated or unavailable data as an ingested measured/official recording.
