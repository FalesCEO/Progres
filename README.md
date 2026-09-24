# Fales — real SPICE playground

An interactive web demo of the existing Fales analog circuit environment. A visitor generates a task, changes a proposal, runs **real server-side ngspice**, and sees the original Fales measurements, per-spec verdicts and reward. No fabricated measurements, browser SPICE emulation or AI agent simulation.

## GitHub Pages

The frontend now builds as a static GitHub Pages site. Start with **[PAGES.md](PAGES.md)** for three-step upload instructions or automatic GitHub Actions deployment. The root `index.html` is a single upload-ready file with embedded CSS, JavaScript, favicon and catalog. Upload just this file. `fales-pages.zip` contains the same single file; regenerate it with `python3 -B scripts/package_pages.py`.

Live simulation still requires the separately hosted Python/ngspice API. Set repository variable `FALES_API_URL` to its HTTPS origin, and set backend environment variable `FALES_ALLOWED_ORIGINS` to your Pages origin. An unconfigured static site shows connection setup and disables simulation rather than fabricating results.

## Run locally with the simulator

With Docker installed:

```sh
docker compose up --build
```

Open **http://localhost:8000**. The image installs ngspice; no API key or model provider is required.

Or locally, with Python 3.12+ and ngspice 39+:

```sh
# macOS
brew install ngspice
# Ubuntu / Debian: sudo apt-get install ngspice
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -B -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

## Original project stays untouched

`vendor/fales/env/` is a byte-for-byte copy of the original project's Python engine and SPICE templates. `vendor/fales/SOURCE.json` records SHA-256 hashes for every copied file. Nothing imports from or writes to `/Users/nazar/Desktop/fales`; that folder is not needed to run or deploy this demo. The snapshot has not been modified.

The adapter changes the engine's **in-memory output-directory setting** before importing the generator. Each request runs in its own process and temporary directory under `.demo-work/api` (or `FALES_DATA_DIR`). Python bytecode writing is disabled. This avoids the engine's per-process working directory colliding across concurrent requests.

## Reused implementation

| Capability | Original implementation |
|---|---|
| Topologies and parameter bounds | `env.circuits.CIRCUITS`, `Circuit.bounds`, `param_names` |
| Task generation | `env.generate.MAKERS` (`make_size_task`, `make_debug_task`, `make_analyze_task`) |
| Legal parameters | `env.core.is_legal` |
| SPICE templates | `Circuit.render_netlist`, the original `.sp` files |
| Simulator and measurement extraction | `env.core.simulate`, each circuit's `parse` |
| Scoring | `env.core.evaluate_task`, `reward`, `spec_score`, `evaluate_analyze` |
| Valid solution | Each generated task's `reference`, or `measured` for analysis |

The registry has **10 topologies, 3 task types, 30 topology/type combinations, and 24 distinct metric keys**. There is no finite claim about the number of generated variations: parameters are sampled and simulated anew on every generation.

The UI derives parameter controls from the registry's names and bounds. Units come from the parameter's actual use in the SPICE skeleton, with explicit handling of on-time, switch resistance, transconductance and input amplitude. No invented parameter ranges are used. All API parameter values are in SI units; the browser converts them for display.

### Task semantics

- **Synthesis:** targets from a freshly sampled, simulated valid solution. The starting proposal is the topology's ordinary reference operating point; it may or may not meet this new task.
- **Repair / Debug:** the generator corrupts exactly one parameter. The original broken-design severity filter is preserved. The visitor sees all editable parameters without disclosure of which one is broken.
- **Analysis:** parameters are fixed; the visitor predicts metrics. ngspice runs during generation, and the existing Fales scorer compares predictions with those measurements. There is one submission per task. Answers remain server-side until submission; results explicitly say they use generation-time measurements rather than claiming a fresh simulation.

**Interactive generation profile:** the original generator runs with random-search rejection budget `0`, without a precomputed pool. This makes on-demand generation practical, particularly for transient-heavy circuits. All physical sanity checks, original target construction and reference-solvability checks remain intact. These tasks are not difficulty-calibrated benchmark samples; an initial proposal can sometimes solve a task. The core reward is unchanged. Generation retries for up to 80 seconds, with a hard 90-second process-group deadline.

Equality requirements display the engine's precise accepted interval `[target × tolerance, target / tolerance]`. Analysis uses the original symmetric ratio threshold of `0.90`. Rewards are displayed to three decimal places; the API returns the original full-precision value.

## API

- `GET /api/catalog` — registered topologies, types and simulator availability.
- `POST /api/generate` — `{ "topology": "ota", "task_type": "size" }`.
- `POST /api/evaluate` — `{ "task_id": "<generated UUID>", "parameters": { ... } }`.
- `POST /api/reference-solution` — `{ "task_id": "<generated UUID>" }`.
- `GET /api/health` — simulator executable availability; not a full simulation test.
- `GET /api/openapi.json` — machine-readable API schema.

Task IDs preserve the exact generated task in SQLite across server restarts. Tasks expire after one hour; storage is capped at 1,000 active tasks. API responses never expose a stored reference during generation. For analysis, the reference endpoint is locked until the first submission.

## Reliability and deployment

Serve the API on a Linux container host or VPS. The frontend can run on GitHub Pages; its workflow builds and publishes only static assets. API/simulation verification and the container build are in a separate workflow.

For production:

1. Deploy the Docker image and persist `/data` using the included Compose volume.
2. Put an HTTPS reverse proxy in front of port 8000. Keep proxy request timeouts at least 100 seconds, set a 16 KB request-body limit, and apply per-client request rate limits appropriate to your traffic.
3. Keep **one Uvicorn worker per container**. The application admits two simulator operations concurrently and rejects excess requests with HTTP 429. Replicas need sticky routing or a shared task service; independent replicas do not share task IDs.
4. Use `/api/health` for availability and the integration suite for full engine verification.

The container runs as an unprivileged user, drops Linux capabilities, has a read-only root filesystem, and limits memory, CPU and processes. Browser input can only supply finite numeric values for registered parameters; arbitrary netlists, commands, file paths and code are not accepted. The original legality check executes before design simulation. Each operation has a hard timeout that terminates its entire process group, including ngspice. Temporary files are cleaned after success or failure. The original engine merges convergence, missing-measurement and simulation-timeout failures into one no-result state; the UI states that limitation rather than inventing a diagnosis.

The frontend uses local HTML/CSS/JavaScript modules with no CDN dependencies, tracks only real evaluation attempts, supports keyboard input and responsive layouts, and clearly marks results as stale after editing a proposal. No optional “AI solver” is shown because the repository's model clients require separate credentials and are not a ready-to-use public solver.

## Verify

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -B -m unittest discover -s tests -v
```

Tests execute real ngspice across all ten topologies, verify valid and failing proposals, compare rewards directly with the original scorer, check single-shot analysis and hidden answers, reject malformed inputs and unknown parameters, check request limits and missing-simulator errors, and verify the engine snapshot hashes. Browser testing covers generation, evaluation, failed metrics, reference loading and responsive rendering.

The local implementation was verified with Python 3.12 and ngspice 47. The Pages workflow is ready but has not been run against a GitHub repository here. API hosting is not provisioned; use the included container deployment on your chosen host.
