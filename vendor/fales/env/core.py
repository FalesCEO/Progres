"""
Fales / analog-env core.

Three functions the whole environment rests on:
    is_legal(params, circuit)          -> (bool, reason)
    simulate(params, circuit)          -> dict | None
    reward(measured, targets, circuit) -> (float, bool)

evaluate_task(task, response) - the dispatcher that picks the right
scoring path from task["type"] ("size" / "debug" / "analyze") and works
with any circuit from the env.circuits registry. This is the single-shot
path: one answer, one reward.

run_episode(client_fn, task) - the multi-step path built ON TOP of those
same three functions: the model tries, the simulator answers with real
measurements, the model corrects itself. See the "episode mode" section
below.

Everything else in the project is a wrapper around these.

The circuit is named by task["circuit"]. Its absence means "ota", so old
task files are read without any conversion.
"""

import json
import math
import os
import re
import shutil
import subprocess

from .circuits import CIRCUITS, DEFAULT, NAMES, get

HERE = os.path.dirname(os.path.abspath(__file__))
WORK_ROOT = os.path.join(os.path.dirname(HERE), "work")

# compatibility with older code and outside scripts: with no argument
# everything behaves exactly as it did before the circuit registry
_OTA = get("ota")
PARAM_NAMES = list(_OTA.param_names)
BOUNDS = dict(_OTA.bounds)
REFERENCE = dict(_OTA.reference)


def _circuit(circuit):
    """Accepts a name, a Circuit object, or None."""
    if circuit is None or isinstance(circuit, str):
        return get(circuit)
    return circuit


def params_of(circuit=None):
    return list(_circuit(circuit).param_names)


def bounds_of(circuit=None):
    return _circuit(circuit).bounds


def reference_of(circuit=None):
    return _circuit(circuit).reference


def metrics_of(circuit=None):
    return _circuit(circuit).metrics


# ---------------------------------------------------------------- legality


def is_legal(params, circuit=None):
    """The check BEFORE simulation. Catches attempts to break the verifier."""
    c = _circuit(circuit)
    if not isinstance(params, dict):
        return False, "params is not a dict"
    for name in c.param_names:
        if name not in params:
            return False, f"missing parameter {name}"
    for name, value in params.items():
        if name not in c.bounds:
            return False, f"unknown parameter {name}"
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, f"{name} is not a number"
        v = float(value)
        if not math.isfinite(v):
            return False, f"{name} is not finite"
        lo, hi = c.bounds[name]
        if not (lo <= v <= hi):
            return False, f"{name}={v:.3e} outside [{lo:.3e}, {hi:.3e}]"
    return True, ""


def render(params, circuit=None):
    return _circuit(circuit).render_netlist(params)


# ---------------------------------------------------------------- simulation


def _read_floats(path, count):
    if not os.path.exists(path):
        return None
    try:
        parts = open(path).read().split()
        if len(parts) < count:
            return None
        vals = [float(x) for x in parts[:count]]
    except (ValueError, OSError):
        return None
    if not all(math.isfinite(v) for v in vals):
        return None
    return vals


def _workdir():
    """
    One directory per process, not per call.

    Every simulation used to create and delete a randomly named directory:
    two extra syscalls for 20 ms of ngspice work, plus a pile of litter in
    work/ after every crash. Now the directory is reused and the old files
    are simply overwritten.
    """
    d = os.path.join(WORK_ROOT, f"p{os.getpid()}")
    os.makedirs(d, exist_ok=True)
    return d


def simulate(params, circuit=None, timeout=None):
    """
    Returns a dict of measured characteristics, or None.

    None means exactly one thing: there is no result. Non-convergence, a
    timeout, illegal parameters - all of it is the same state with reward
    0. No exceptions escape: in an RL loop an exception halts training.
    """
    c = _circuit(circuit)
    ok, _ = is_legal(params, c)
    if not ok:
        return None

    workdir = _workdir()
    # old results have to go, otherwise a failed simulation quietly hands
    # back the numbers from the previous run
    for fname, _ in c.outputs:
        try:
            os.remove(os.path.join(workdir, fname))
        except OSError:
            pass

    with open(os.path.join(workdir, "c.sp"), "w") as f:
        f.write(c.render_netlist(params))
    try:
        subprocess.run(
            ["ngspice", "-b", "c.sp"],
            cwd=workdir, timeout=timeout or c.timeout,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    files = {}
    for fname, count in c.outputs:
        vals = _read_floats(os.path.join(workdir, fname), count)
        if vals is None:
            return None
        files[fname] = vals

    m = c.parse(files)
    if m is None:
        return None
    if not all(isinstance(v, (int, float)) and math.isfinite(v)
               for v in m.values()):
        return None
    return {k: float(v) for k, v in m.items()}


def cleanup_workdirs():
    """
    Removes the per-process directories (p<pid>). Called at the end of
    generation and of the baselines. Leaves everything else in work/ alone
    (the pool cache, for instance).
    """
    if not os.path.isdir(WORK_ROOT):
        return
    for name in os.listdir(WORK_ROOT):
        path = os.path.join(WORK_ROOT, name)
        if os.path.isdir(path) and name.startswith("p") and name[1:].isdigit():
            shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------- reward


def spec_score(metric, value, target, circuit=None):
    """
    The partial score of one requirement, in [0, 1].

    These are the most important lines in the project. A binary reward
    (pass / fail) does not work: the model will never hit every spec by
    accident, will always get zero, and will learn nothing. A logarithmic
    scale gives a gradient: moving in the right direction raises the score
    before the spec is even met.

    For "eq" (reference voltage, hysteresis width) the ratio is symmetric
    and divided by the tolerance: land inside the tolerance and you get
    one, miss it and you get the same logarithmic scale in both
    directions.
    """
    if isinstance(metric, str):
        metric = _circuit(circuit).metric(metric)
    if metric.direction == "min":
        ratio = value / target if target != 0 else 0.0
    elif metric.direction == "max":
        ratio = target / value if value != 0 else 0.0
    else:
        if value <= 0 or target <= 0:
            ratio = 0.0
        else:
            ratio = (min(value, target) / max(value, target)) / metric.tol
    if ratio >= 1.0:
        return 1.0
    if ratio <= 0.0:
        return 0.0
    return max(0.0, 1.0 + math.log10(max(ratio, 1e-3)) / 3.0)


def reward(measured, targets, circuit=None):
    """Returns (reward 0..1.5, whether it is solved)."""
    if measured is None:
        return 0.0, False
    c = _circuit(circuit)
    scores = []
    for name in targets:
        if name not in measured:
            return 0.0, False
        scores.append(spec_score(c.metric(name), measured[name], targets[name]))
    if not scores:
        return 0.0, False
    solved = all(s >= 1.0 for s in scores)
    partial = sum(scores) / len(scores)
    return partial + (0.5 if solved else 0.0), solved


def evaluate(params, targets, circuit=None):
    """The full cycle: legality -> simulation -> reward."""
    c = _circuit(circuit)
    ok, why = is_legal(params, c)
    if not ok:
        return {"reward": 0.0, "solved": False,
                "measured": None, "error": f"illegal: {why}"}
    m = simulate(params, c)
    if m is None:
        return {"reward": 0.0, "solved": False,
                "measured": None, "error": "simulation failed"}
    r, solved = reward(m, targets, c)
    return {"reward": r, "solved": solved, "measured": m, "error": None}


# ---------------------------------------------------------------- analysis (task type "analyze")

ANALYZE_TOL = 0.9  # predicted/actual ratio (symmetric) below which it is not "solved"


def _closeness(pred, actual):
    """Symmetric pred/actual ratio in (0, 1], or None if pred is invalid."""
    if not isinstance(pred, (int, float)) or isinstance(pred, bool):
        return None
    pf = float(pred)
    if not math.isfinite(pf) or pf <= 0 or actual <= 0:
        return None
    return min(pf, actual) / max(pf, actual)


def evaluate_analyze(predicted, actual):
    """
    Scoring for task type "analyze": the model predicts the measured
    characteristics WITHOUT access to the simulator. The simulator is only
    the source of truth for the comparison - the answer itself is never
    simulated.

    The same logarithmic scale as spec_score, but symmetric: an
    underestimate and an overestimate are penalised equally.
    """
    if not isinstance(predicted, dict):
        return {"reward": 0.0, "solved": False, "scores": None,
                "error": "predicted is not a dict"}
    ratios = {k: _closeness(predicted.get(k), v) for k, v in actual.items()}
    scores = {k: (0.0 if r is None
                  else max(0.0, 1.0 + math.log10(max(r, 1e-3)) / 3.0))
              for k, r in ratios.items()}
    solved = all(r is not None and r >= ANALYZE_TOL for r in ratios.values())
    partial = sum(scores.values()) / len(scores)
    return {"reward": partial + (0.5 if solved else 0.0), "solved": solved,
            "scores": scores, "error": None}


# ---------------------------------------------------------------- task type dispatcher


def task_circuit(task):
    return get(task.get("circuit", DEFAULT))


def evaluate_task(task, response):
    """
    The single scoring entry point, independent of task type and circuit.

    "size" and "debug" both return a full parameter set and are scored by
    the same evaluate() against task["targets"] - "debug" simply has fewer
    degrees of freedom, since every value but one is already given.
    "analyze" returns predicted characteristics and is scored by
    evaluate_analyze() against task["measured"].
    """
    ttype = task.get("type", "size")
    if ttype in ("size", "debug"):
        return evaluate(response, task["targets"], task_circuit(task))
    if ttype == "analyze":
        return evaluate_analyze(response, task["measured"])
    return {"reward": 0.0, "solved": False,
            "error": f"unknown task type: {ttype}"}


# ---------------------------------------------------------------- parsing the model reply


def extract_json(text):
    """Extracts JSON even when the model wrapped it in prose or fences."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(),
                  flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    return None


def coerce(obj):
    """Coerces values to float. Models often write '20u' instead of 2e-5."""
    if not isinstance(obj, dict):
        return None
    suffix = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6,
              "m": 1e-3, "k": 1e3, "K": 1e3, "meg": 1e6, "M": 1e6, "g": 1e9}
    out = {}
    for k, v in obj.items():
        if isinstance(v, (int, float)):
            out[k] = float(v)
        elif isinstance(v, str):
            s = v.strip()
            m = re.match(r"^([-+]?[\d.]+(?:[eE][-+]?\d+)?)\s*"
                         r"(meg|[fpnuµmkKMg])?", s)
            if not m:
                return None
            val = float(m.group(1))
            if m.group(2):
                val *= suffix.get(m.group(2), 1.0)
            out[k] = val
        else:
            return None
    return out


# ---------------------------------------------------------------- episode mode

"""
Multi-step mode.

Single-shot scoring is not an RL environment, it is an eval: the model
sees the problem, hands back an answer, gets a number, and that is all.
What appears here is the thing that is missing there - a trajectory. The
model makes an attempt, the SIMULATOR answers with real measurements, the
model corrects itself. A verified rollout like this is exactly what labs
buy, so the trajectory is stored in full, dialogue included.

Every circuit is supported in two task types: "size" (design from
scratch) and "debug" (find and fix the corrupted parameter). Both are
searches through parameter space, and simulator feedback gives both of
them precisely what they lack.

"analyze" is not supported and never will be: that task is about
analytical understanding of a circuit WITHOUT a simulator. Feeding
measurements in between steps would cancel the task itself - the model
would simply copy the answer out of the feedback. Type "analyze" stays
single-shot forever.

run_episode is a layer ON TOP of is_legal/simulate/reward, not a
replacement for them; --mode single keeps working alongside, unchanged.
"""

EPISODE_TYPES = ("size", "debug")
EPISODE_TASKS = {(c, t) for c in NAMES for t in EPISODE_TYPES}
EPISODE_STEP_BONUS = 0.05      # per step saved, and only when solved
EPISODE_MAX_STEPS = 8

EPISODE_INTRO = """You are sizing a {title} in SPICE, over at most {max_steps} attempts.

This is an interactive loop, not a single shot. After every attempt the
circuit is really simulated in ngspice and you get the measured results
back. Use them to correct the next attempt.

Netlist:
{skeleton}

{models}

{hint}Meet ALL of these specifications:
{specs}

Allowed ranges (SI units):
{bounds}

Reply with ONLY a JSON object, no explanation and no markdown fences:
{keys}
Add "final": true to that object when you are confident and want to stop
early. This is attempt 1 of {max_steps}."""

EPISODE_INTRO_DEBUG = """You are debugging a {title} in SPICE, over at most {max_steps} attempts.

The topology is FIXED. All {n} parameters below have a value, but exactly
ONE of them was corrupted (changed to a bad value) - that is why the
circuit misses spec. Find the broken parameter and correct it. Usually
only one value needs to change; copy the rest as-is.

This is an interactive loop, not a single shot. After every attempt the
circuit is really simulated in ngspice and you get the measured results
back. Use them to narrow down which parameter is the broken one.

Netlist (current, one value is broken):
{skeleton}

{models}

{hint}{measured_block}Required specs:
{specs}

Allowed ranges (SI units):
{bounds}

Reply with ONLY a JSON object with all {n} keys, SI floats - the corrected
design. No explanation and no markdown fences:
{keys}
Add "final": true to that object when you are confident and want to stop
early. This is attempt 1 of {max_steps}."""

EPISODE_FEEDBACK = """Attempt {step} simulated. Measured:
{results}
{verdict}

This is attempt {next_step} of {max_steps}. Reply with ONLY a corrected
JSON object with the same keys, or add "final": true to stop here."""

EPISODE_REJECTED = """Attempt {step} was not simulated: the parameters were
outside the allowed ranges or malformed. Details: {why}

This is attempt {next_step} of {max_steps}. Reply with ONLY a corrected
JSON object with the same keys, all values inside the allowed ranges."""

EPISODE_NO_CONVERGE = """Attempt {step} did not converge in ngspice, so there
are no measurements. Values that extreme break the operating point - move
back towards the middle of the allowed ranges.

This is attempt {next_step} of {max_steps}. Reply with ONLY a corrected
JSON object with the same keys."""

EPISODE_NO_JSON = """No JSON object was found in that reply. Reply with ONLY a
JSON object with the keys {keys_short}, values as SI floats, nothing else."""


def supports_episode(task):
    """Whether this task can be run in episode mode."""
    return (task.get("circuit", DEFAULT),
            task.get("type", "size")) in EPISODE_TASKS


def _feedback_line(metric, value, target):
    """One feedback line: what was measured, what is required, does it pass."""
    got, need = metric.show(value), metric.show(target)
    score = spec_score(metric, value, target)
    if score >= 1.0:
        verdict = "ok"
    elif metric.direction == "min":
        verdict = f"short by {100.0 * (1.0 - value / target):.1f}%"
    elif metric.direction == "max":
        verdict = f"over by {100.0 * (value / target - 1.0):.1f}%"
    else:
        off = abs(value - target) / target * 100.0 if target else 0.0
        verdict = f"off by {off:.1f}%"
    tol = (f" +/-{(1.0 - metric.tol) * 100:.0f}%"
           if metric.direction == "eq" else "")
    return (f"  {metric.name}: got {got} {metric.unit}, "
            f"need {metric.op} {need} {metric.unit}{tol} ({verdict})")


def episode_feedback(circuit, measured, targets):
    """Simulator measurements in human form - the thing an eval never gives."""
    lines = [_feedback_line(circuit.metric(k), measured[k], targets[k])
             for k in targets]
    missing = [k for k in targets
               if spec_score(circuit.metric(k), measured[k], targets[k]) < 1.0]
    if missing:
        verdict = (f"{len(missing)} of {len(targets)} specs still missing: "
                   f"{', '.join(missing)}.")
    else:
        verdict = "All specs met."
    return "\n".join(lines), verdict


def _illegal_detail(params, circuit):
    """
A model-facing explanation of why the parameter set was rejected.

    is_legal() returns a terse internal reason meant for logs. The prompt
    needs the same fact spelled out the way the rest of the prompt reads,
    so it is composed here rather than rewritten inside is_legal.
    """
    if not isinstance(params, dict):
        return "the reply was not a JSON object of parameters"
    missing = [k for k in circuit.param_names if k not in params]
    if missing:
        return f"missing keys: {', '.join(missing)}"
    extra = [k for k in params if k not in circuit.bounds]
    if extra:
        return f"unknown keys: {', '.join(extra)}"
    bad = []
    for name in circuit.param_names:
        v = params[name]
        if isinstance(v, bool) or not isinstance(v, (int, float)) \
                or not math.isfinite(float(v)):
            bad.append(f"{name} is not a finite number")
            continue
        lo, hi = circuit.bounds[name]
        if not (lo <= float(v) <= hi):
            bad.append(f"{name}={float(v):.4g} is outside "
                       f"[{lo:.4g}, {hi:.4g}]")
    return "; ".join(bad) if bad else "parameters rejected"


def _parse_step(text):
    """
    Model reply -> (parameters or None, whether it asks to stop).

    "final" is popped BEFORE coerce: in Python bool is a subclass of int,
    so otherwise the flag would quietly turn into a parameter of value 1.0.
    """
    obj = extract_json(text)
    if not isinstance(obj, dict):
        return None, False
    final = bool(obj.pop("final", False)) or bool(obj.pop("done", False))
    if not obj:
        return None, final
    return coerce(obj), final


def episode_intro(task, max_steps=EPISODE_MAX_STEPS):
    """
    The first prompt of an episode. Differs by task type.

    "size" - design from scratch against the given specs.
    "debug" - here is the complete circuit, exactly one parameter is
    corrupted, find it and fix it. What is shown is THE BROKEN variant
    together with its failing measurements, exactly as in the single-shot
    debug prompt.

    From step two onward both types behave identically: the same
    episode_feedback carrying simulator measurements.
    """
    c = task_circuit(task)
    targets = task["targets"]
    hint = f"Note: {c.hint}\n\n" if c.hint else ""
    if task.get("type", "size") == "debug":
        bm = task.get("broken_measured")
        measured_block = (
            "Currently measured (broken, fails spec):\n"
            + c.measured_block(bm) + "\n\n" if bm else
            "Currently: the simulation does not even converge.\n\n")
        return EPISODE_INTRO_DEBUG.format(
            title=c.title, max_steps=max_steps, n=len(c.param_names),
            skeleton=c.render_skeleton(task["broken_params"]),
            models=c.models_block, hint=hint, measured_block=measured_block,
            specs=c.spec_block(targets), bounds=c.bounds_block(),
            keys=c.keys_block())
    return EPISODE_INTRO.format(
        title=c.title, max_steps=max_steps, skeleton=c.skeleton,
        models=c.models_block, hint=hint, specs=c.spec_block(targets),
        bounds=c.bounds_block(), keys=c.keys_block())


def run_episode(client_fn, task, max_steps=EPISODE_MAX_STEPS):
    """
    A multi-step episode: the model designs, the simulator answers.

    client_fn(messages) -> reply text. The abstraction is deliberate: the
    core knows about no API at all, so the very same loop runs against
    Anthropic, against a local model, and against a stub in the tests.

    Returns an episode record fit for export as training data - one JSON
    object per episode (see dump_episodes).

    The episode reward is the best reward ACROSS ALL STEPS, not the last
    one: the model may have found a solution at step 3 and ruined it at
    step 5. Plus a bonus for steps saved - but ONLY when the task is
    solved. Otherwise the bonus would pay for an early "final" on a bad
    design, that is, for giving up sooner.
    """
    if not supports_episode(task):
        raise ValueError(
            f"episode mode is only supported for "
            f"{sorted(EPISODE_TASKS)}, not for "
            f"({task.get('circuit', DEFAULT)}, {task.get('type', 'size')})")

    circuit = task_circuit(task)
    targets = task["targets"]
    messages = [{"role": "user",
                 "content": episode_intro(task, max_steps)}]

    steps, stopped = [], "max_steps"
    for i in range(1, max_steps + 1):
        text = client_fn(messages)
        messages.append({"role": "assistant", "content": text or ""})
        params, final = _parse_step(text)

        if params is None:
            if final:
                stopped = "final"
                break
            steps.append({"step": i, "params": None, "measured": None,
                          "reward": 0.0, "solved": False,
                          "error": "parse failed"})
            if i == max_steps:
                stopped = "no_json"
                break
            messages.append({"role": "user", "content": EPISODE_NO_JSON.format(
                keys_short=", ".join(circuit.param_names))})
            continue

        ok, why = is_legal(params, circuit)
        measured = simulate(params, circuit) if ok else None
        r, solved = reward(measured, targets, circuit)
        error = (None if measured is not None
                 else (f"illegal: {why}" if not ok else "simulation failed"))
        steps.append({"step": i, "params": params, "measured": measured,
                      "reward": r, "solved": solved, "error": error})

        if solved:
            stopped = "solved"
            break
        if final:
            stopped = "final"
            break
        if i == max_steps:
            break

        nxt = {"step": i, "next_step": i + 1, "max_steps": max_steps}
        if not ok:
            content = EPISODE_REJECTED.format(
                why=_illegal_detail(params, circuit), **nxt)
        elif measured is None:
            content = EPISODE_NO_CONVERGE.format(**nxt)
        else:
            results, verdict = episode_feedback(circuit, measured, targets)
            content = EPISODE_FEEDBACK.format(results=results,
                                              verdict=verdict, **nxt)
        messages.append({"role": "user", "content": content})

    return _finish_episode(task, steps, messages, max_steps, stopped)


def _finish_episode(task, steps, messages, max_steps, stopped):
    solved_steps = [s for s in steps if s["solved"]]
    solve_step = solved_steps[0]["step"] if solved_steps else None
    best = max((s["reward"] for s in steps), default=0.0)
    best_step = next((s for s in steps if s["reward"] == best), None)
    # bonus for solved episodes only: otherwise it would pay for giving up
    bonus = (EPISODE_STEP_BONUS * (max_steps - solve_step)
             if solve_step is not None else 0.0)
    return {
        "circuit": task.get("circuit", DEFAULT),
        "type": task.get("type", "size"),
        "targets": task["targets"],
        "difficulty": task.get("difficulty"),
        "max_steps": max_steps,
        "n_steps": len(steps),
        "steps": steps,
        "solved": solve_step is not None,
        "solve_step": solve_step,
        "best_reward": best,
        "best_params": best_step["params"] if best_step else None,
        "efficiency_bonus": bonus,
        "episode_reward": best + bonus,
        "stopped": stopped,
        "messages": messages,
    }


def episode_result(episode):
    """
    Episode record -> a result in the same shape as the single-shot one.

    Needed by both bench.py and manual_eval.py: summaries, pass@1 and
    plot.py are computed identically whether the model went through an API
    or a human pasted the answers by hand.

    "error" is the last real failure (illegal parameters, non-convergence,
    unparseable JSON), but ONLY if the episode was never solved. A failed
    step inside a solved episode is not a run error, it is a normal part of
    the trajectory: getting feedback in order to correct itself is exactly
    what the model is there for. An empty steps list means no step
    happened at all.
    """
    last_error = next((s["error"] for s in reversed(episode["steps"])
                       if s.get("error")), None)
    if not episode["steps"]:
        error = "no steps"
    elif episode["solved"]:
        error = None
    else:
        error = last_error
    return {
        "reward": episode["episode_reward"],
        "solved": episode["solved"],
        "params": episode["best_params"],
        "n_steps": episode["n_steps"],
        "solve_step": episode["solve_step"],
        "best_reward": episode["best_reward"],
        "efficiency_bonus": episode["efficiency_bonus"],
        "stopped": episode["stopped"],
        "error": error,
    }


def dump_episodes(path, episodes):
    """One episode, one JSON line. The export format for training data."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        for ep in episodes:
            f.write(json.dumps(ep, ensure_ascii=False) + "\n")
    return path


# compatibility with older scripts that imported straight from core
DIRECTION = {m.name: m.direction for m in _OTA.metrics}
