"""
Task generator. Three types, five topologies.

Types:
  size     - synthesis. Target characteristics are given, all circuit
             parameters have to be chosen.
  debug    - repair. Parameters are given, EXACTLY ONE of them is
             corrupted, along with the current (failing) measurements.
             The broken parameter has to be found and fixed.
  analyze  - analysis. Every parameter is given (a fully specified
             circuit). The characteristics have to be predicted WITHOUT
             a simulator.

Topologies come from the env.circuits registry and run from simple to
hard: diffamp -> ota -> bandgap -> ldo -> comparator. The last three are
not "more transistors" but different skills: temperature stability, loop
stability with PSRR, the time domain.

Idea 1 (for size and debug): tasks are built BACKWARDS - from the
solution to the problem statement. Take a valid configuration, simulate
it, and declare the achieved characteristics, slightly relaxed, to be the
target. That way every task is guaranteed to have a solution, and we hold
that solution in our hands.

Idea 2 (critical): a task that random search solves is thrown away.
Without this filter the generator produces trivial tasks - verified
experimentally: at slack 0.55-0.92 random search with 20 attempts solved
67% of the tasks, and the benchmark proved nothing.

Each type has its own filter, because "random guessing" means something
different in each:

  size   - a sample of REJECT_BUDGET measurements from the pool (see
           idea 3). It is pure arithmetic, so the budget can stay large.
  debug  - BROKEN_MAX_REWARD: the broken variant has to fail DECISIVELY,
           not barely. A barely failing circuit makes a bad debug task:
           its tolerance window is so wide that almost any random change
           to almost any parameter drags it back into spec, and a blind
           "repairman" solves it by luck rather than by reasoning. The
           check is free: the broken variant's measurements are computed
           anyway. On top of it there is the optional REPAIR_BUDGET - a
           direct run of the blind repairman - but that costs real
           simulations, so it is off by default.

Idea 3 (speed): the filter from idea 2 used to launch REJECT_BUDGET fresh
simulations for EVERY candidate - 80 ngspice runs for a single
keep-or-drop decision, and that is what ate 95% of generation time. Now
random search is simulated once per circuit as a pool of measurements
(failures included - their share matters too), and candidates simply draw
a sample from it. Same distribution, two orders of magnitude fewer
simulations. The pool is cached on disk keyed by the netlist and bounds.

Targets are ALWAYS rounded towards the safe side; otherwise, at slack
close to 1.0, the reference solution fails its own task.
"""

import argparse
import json
import math
import multiprocessing as mp
import os
import random
import time

from . import circuits as circuit_registry
from .core import WORK_ROOT, _circuit, cleanup_workdirs, reward, simulate

SLACK_RANGE = (0.97, 1.0)
REJECT_BUDGET = 200    # size of the pool sample used to reject ("size")
POOL_SIZE = 900        # random attempts simulated per circuit
BREAK_FACTOR_RANGE = (4.0, 30.0)   # factor a parameter is broken by ("debug")
REPAIR_BUDGET = 0      # REAL simulations per candidate ("debug"), optional
BROKEN_MAX_REWARD = 0.95   # how badly it has to be broken ("debug")

POOL_DIR = os.path.join(WORK_ROOT, "pools")


def _sig(x, n=4):
    if x == 0:
        return 0.0
    return round(x, -int(math.floor(math.log10(abs(x)))) + (n - 1))


def _round_down(x, n=4):
    r = _sig(x, n)
    return r if r <= x else _sig(x * (1 - 10 ** -(n - 1)), n)


def _round_up(x, n=4):
    r = _sig(x, n)
    return r if r >= x else _sig(x * (1 + 10 ** -(n - 1)), n)


# ---------------------------------------------------------------- sampling


def sample_wide(circuit):
    p = {}
    for name in circuit.param_names:
        lo, hi = circuit.bounds[name]
        p[name] = math.exp(random.uniform(math.log(lo), math.log(hi)))
    return p


def sample_around(circuit, spread=1.2):
    p = {}
    for name in circuit.param_names:
        lo, hi = circuit.bounds[name]
        v = circuit.reference[name] * math.exp(random.uniform(-spread, spread))
        p[name] = min(max(v, lo), hi)
    return p


def sample_mixed(circuit=None, wide_prob=0.35):
    c = _circuit(circuit)
    return sample_wide(c) if random.random() < wide_prob else sample_around(c)


def is_sane(m, circuit):
    if m is None:
        return False
    return all(met.sanity[0] <= m[met.name] <= met.sanity[1]
               for met in circuit.metrics)


def make_targets(circuit, m, slack):
    """
    Relaxed achieved characteristics -> the task requirements.

    "min"/"max" are relaxed by slack and rounded towards the safe side.
    "eq" is not relaxed at all: difficulty there is set by the metric's
    tolerance, and the target is merely rounded to a few significant
    digits so the prompt reads "1.28 V" and not "1.278073 V".
    """
    t = {}
    for met in circuit.metrics:
        v = m[met.name]
        if met.direction == "min":
            v = v * slack
            if met.cap is not None:
                v = min(v, met.cap)
            t[met.name] = _round_down(v)
        elif met.direction == "max":
            t[met.name] = _round_up(v / slack)
        else:
            t[met.name] = _sig(v, met.eq_sig)
    return t


# ---------------------------------------------------------------- random search pool


def _pool_key(circuit):
    # the same fingerprint that is stamped into tasks.json: change the
    # netlist or the bounds and both the pool cache and the dataset go
    # stale together
    return circuit.fingerprint


def _pool_path(circuit):
    return os.path.join(POOL_DIR, f"{circuit.name}-{_pool_key(circuit)}.json")


def _pool_worker(args):
    """One random attempt. None is a result too: the failure rate matters."""
    cname, seed = args
    random.seed(seed)
    c = circuit_registry.get(cname)
    return simulate(sample_mixed(c), c)


def build_pool(circuit, size, workers, use_cache=True):
    """
    The pool of random-search measurements - one per circuit, not per task.

    It contains None entries (non-converging attempts) as well: the filter
    has to see the same failure rate a real random search would see.
    """
    path = _pool_path(circuit)
    if use_cache and os.path.exists(path):
        try:
            pool = json.load(open(path))
            if len(pool) >= size:
                print(f"  [{circuit.name}] pool from cache: {len(pool)}")
                return pool
        except (OSError, ValueError):
            pass

    t0 = time.time()
    with mp.Pool(workers) as p:
        pool = list(p.imap_unordered(
            _pool_worker,
            [(circuit.name, 900_000_000 + i) for i in range(size)],
            chunksize=8,
        ))
    ok = sum(1 for m in pool if m is not None)
    print(f"  [{circuit.name}] pool: {size} attempts, {ok} converged "
          f"({time.time() - t0:.1f} s)")

    os.makedirs(POOL_DIR, exist_ok=True)
    try:
        json.dump(pool, open(path, "w"))
    except OSError:
        pass
    return pool


def random_search_solves(targets, circuit, pool, budget=REJECT_BUDGET):
    """Would a random sample of budget attempts solve this task."""
    if not pool:
        return False
    sample = random.sample(pool, min(budget, len(pool)))
    for m in sample:
        if m is None:
            continue
        if reward(m, targets, circuit)[1]:
            return True
    return False


# ---------------------------------------------------------------- type "size"


def make_size_task(circuit, pool=None, reject_budget=REJECT_BUDGET,
                   slack_range=None):
    params = sample_mixed(circuit)
    m = simulate(params, circuit)
    if not is_sane(m, circuit):
        return None

    slack = random.uniform(*(slack_range or SLACK_RANGE))
    targets = make_targets(circuit, m, slack)

    # the reference is obliged to pass its own task
    if not reward(m, targets, circuit)[1]:
        return None

    # trivial tasks are thrown away
    if reject_budget and random_search_solves(targets, circuit, pool,
                                              reject_budget):
        return None

    return {
        "type": "size",
        "circuit": circuit.name,
        "targets": targets,
        "reference": params,
        "reference_measured": m,
        "difficulty": round(slack, 3),
    }


# ---------------------------------------------------------------- type "debug"


def _break_one_param(circuit, params):
    """Corrupts exactly one parameter of params. Returns (name, new_value),
    or None if a reasonable number of attempts did not manage it."""
    names = list(circuit.param_names)
    random.shuffle(names)
    for name in names:
        lo, hi = circuit.bounds[name]
        orig = params[name]
        for _ in range(20):
            factor = random.uniform(*BREAK_FACTOR_RANGE)
            if random.random() < 0.5:
                factor = 1.0 / factor
            broken = min(max(orig * factor, lo), hi)
            if broken > 0 and abs(math.log10(broken / orig)) > 0.3:
                return name, broken
    return None


def repair_search_solves(targets, circuit, broken_params, budget):
    """
    Would a blind "repairman" fix the circuit within budget attempts.

    This is EXACTLY the agent that computes the random@N baseline for type
    "debug" (baselines.py:_rand_size_or_debug): it does not know which
    parameter is broken, so each time it picks one at random and throws a
    random in-bounds value at it. Filter and baseline are deliberately
    identical - otherwise the filter would reject something other than
    what is later measured.

    Unlike the filter for "size", the pool is of no use here: every
    attempt depends on the specific broken_params, so these are real
    simulations. Hence the smaller budget.
    """
    for _ in range(budget):
        name = random.choice(circuit.param_names)
        lo, hi = circuit.bounds[name]
        trial = dict(broken_params)
        trial[name] = math.exp(random.uniform(math.log(lo), math.log(hi)))
        m = simulate(trial, circuit)
        if m is None:
            continue
        if reward(m, targets, circuit)[1]:
            return True
    return False


def make_debug_task(circuit, pool=None, repair_budget=REPAIR_BUDGET,
                    slack_range=None, broken_max=BROKEN_MAX_REWARD):
    params = sample_mixed(circuit)
    m = simulate(params, circuit)
    if not is_sane(m, circuit):
        return None

    slack = random.uniform(*(slack_range or SLACK_RANGE))
    targets = make_targets(circuit, m, slack)

    if not reward(m, targets, circuit)[1]:
        return None

    broke = _break_one_param(circuit, params)
    if broke is None:
        return None
    broken_name, broken_value = broke
    broken_params = dict(params)
    broken_params[broken_name] = broken_value

    bm = simulate(broken_params, circuit)
    if bm is not None:
        br, bsolved = reward(bm, targets, circuit)
        if bsolved:
            # the break is not serious enough - "change nothing" would
            # have solved it anyway, so the candidate is unusable
            return None
        if br > broken_max:
            # a barely failing circuit makes a bad debug task: almost any
            # random change to almost any parameter drags it back into
            # spec, and a blind "repairman" solves it not by reasoning but
            # because the tolerance window is wide. The check is free: bm
            # has already been computed above.
            return None

    # trivial tasks are thrown away - same as for "size", only with the
    # agent that is appropriate for "debug"
    if repair_budget and repair_search_solves(targets, circuit,
                                              broken_params, repair_budget):
        return None

    return {
        "type": "debug",
        "circuit": circuit.name,
        "targets": targets,
        "broken_params": broken_params,
        "broken_measured": bm,          # None if the broken variant does not converge
        "broken_param": broken_name,    # for analysis only - never shown in the prompt
        "reference": params,
        "reference_measured": m,
        "difficulty": round(slack, 3),
    }


# ---------------------------------------------------------------- type "analyze"


def make_analyze_task(circuit, pool=None, reject_budget=0, slack_range=None):
    params = sample_mixed(circuit)
    m = simulate(params, circuit)
    if not is_sane(m, circuit):
        return None
    return {
        "type": "analyze",
        "circuit": circuit.name,
        "params": params,
        "measured": m,
    }


# ---------------------------------------------------------------- generation

MAKERS = {
    "size": make_size_task,
    "debug": make_debug_task,
    "analyze": make_analyze_task,
}

_CTX = {}


def _init(cname, pool, budget, slack_range, broken_max):
    # module constants do not reach the workers: on macOS Pool starts via
    # spawn and every process imports env.generate afresh, with the values
    # from the file. So everything set from the CLI is passed in here
    # explicitly.
    _CTX["circuit"] = circuit_registry.get(cname)
    _CTX["pool"] = pool
    _CTX["budget"] = budget
    _CTX["slack_range"] = slack_range
    _CTX["broken_max"] = broken_max


def _worker(args):
    task_type, seed = args
    random.seed(seed)
    kw = ({"broken_max": _CTX["broken_max"]} if task_type == "debug" else {})
    return MAKERS[task_type](_CTX["circuit"], _CTX["pool"], _CTX["budget"],
                             _CTX["slack_range"], **kw)


def generate(n, circuit, task_type, pool, workers, seed0=0,
             reject_budget=REJECT_BUDGET, repair_budget=REPAIR_BUDGET,
             slack_range=None, broken_max=BROKEN_MAX_REWARD):
    tasks, tried = [], 0
    # the maker's third argument means different things per type: for
    # "size" it is the pool sample size (free), for "debug" the number of
    # real simulations the blind repairman gets
    budget = {"size": reject_budget, "debug": repair_budget}.get(task_type, 0)
    with mp.Pool(workers, initializer=_init,
                 initargs=(circuit.name, pool, budget, slack_range,
                           broken_max)) as p:
        while len(tasks) < n:
            batch = [(task_type, seed0 + tried + i) for i in range(n * 3)]
            # count the attempts CONSUMED, not the batch size: the loop
            # exits as soon as n tasks are collected, so the batch is
            # usually never finished. The yield used to be computed
            # against n*3 and therefore could never exceed 33.3% - that
            # was a ceiling of the accounting, not a property of the
            # generator
            for t in p.imap_unordered(_worker, batch, chunksize=4):
                tried += 1
                if t is not None:
                    tasks.append(t)
                    if len(tasks) >= n:
                        break
            print(f"  [{circuit.name}/{task_type}] {len(tasks)}/{n} tasks, "
                  f"attempts: {tried}", flush=True)
    return tasks[:n], tried


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=60,
                    help="number of tasks PER (circuit, type) pair")
    ap.add_argument("--circuits", nargs="+", default=list(circuit_registry.NAMES),
                    choices=list(circuit_registry.NAMES))
    ap.add_argument("--types", nargs="+", default=["size", "debug", "analyze"],
                    choices=list(MAKERS))
    ap.add_argument("-o", default="tasks.json")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pool", type=int, default=POOL_SIZE,
                    help="size of the random-search pool per circuit")
    ap.add_argument("--reject-budget", type=int, default=REJECT_BUDGET,
                    help="trivial-task filter for 'size': the pool sample "
                         "size. Free; 0 disables it.")
    ap.add_argument("--repair-budget", type=int, default=REPAIR_BUDGET,
                    help="trivial-task filter for 'debug': this many REAL "
                         "simulations per candidate. Costs generation "
                         "time; 0 disables it.")
    ap.add_argument("--broken-max", type=float, default=BROKEN_MAX_REWARD,
                    help="maximum reward of the broken variant for "
                         "'debug'. Lower means harsher selection of "
                         "breaks, for free. 1.5 disables it in practice.")
    ap.add_argument("--slack", type=float, nargs=2, default=list(SLACK_RANGE),
                    metavar=("LO", "HI"),
                    help="range the targets are relaxed by. Closer to 1.0 "
                         "means harder specs and a lower random-search "
                         "baseline, but a lower generator yield too.")
    ap.add_argument("--no-cache", action="store_true",
                    help="do not use cached pools")
    args = ap.parse_args()

    workers = args.workers or max(1, mp.cpu_count())
    t_start = time.time()
    all_tasks = []
    stats = {}

    need_pool = "size" in args.types and args.reject_budget > 0
    for ci, cname in enumerate(args.circuits):
        circuit = circuit_registry.get(cname)
        print(f"\n=== circuit '{cname}' - {circuit.summary} ===")
        pool = (build_pool(circuit, args.pool, workers, not args.no_cache)
                if need_pool else [])
        for ti, ttype in enumerate(args.types):
            # a separate seed range per (circuit, type) pair, so that the
            # generators of different circuits do not correlate
            seed0 = args.seed + ci * 100_000_000 + ti * 10_000_000
            tasks, tried = generate(args.n, circuit, ttype, pool, workers,
                                    seed0=seed0,
                                    reject_budget=args.reject_budget,
                                    repair_budget=args.repair_budget,
                                    slack_range=tuple(args.slack),
                                    broken_max=args.broken_max)
            stats[(cname, ttype)] = (len(tasks), tried)
            all_tasks.extend(tasks)

    random.Random(args.seed).shuffle(all_tasks)
    n_test = max(1, len(all_tasks) // 2)
    split = {"train": all_tasks[n_test:], "test": all_tasks[:n_test],
             "circuits": circuit_registry.stamp()}
    with open(args.o, "w") as f:
        json.dump(split, f, indent=1)

    print(f"\nSaved {args.o}: "
          f"train={len(split['train'])}, test={len(split['test'])}")
    print(f"{'circuit':<12}{'type':<10}{'tasks':>7}{'yield':>9}")
    for (cname, ttype), (got, tried) in stats.items():
        print(f"{cname:<12}{ttype:<10}{got:>7}{100.0*got/max(tried,1):>8.1f}%")
    print(f"\nTime: {time.time() - t_start:.1f} s")
    cleanup_workdirs()


if __name__ == "__main__":
    main()
