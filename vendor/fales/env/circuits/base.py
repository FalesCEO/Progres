"""
The description of a single circuit. Everything the environment needs to
know about a topology lives in one Circuit object - and nowhere else.

Adding a new circuit = one module with one Circuit and one .sp file. No
other file in the project changes: core.py, generate.py, bench.py and
baselines.py all work through these fields and never learn circuit names.
"""

import hashlib
import os
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))


def load_netlist(filename):
    with open(os.path.join(HERE, filename)) as f:
        return f.read()


# The models block for prompts (the .sp files spell the models out in
# full, so every netlist runs in ngspice as is, with no assembly step).
MOS_MODELS_PROMPT = """Models: LEVEL=1 MOSFETs.
  NMOS: VTO=0.7  KP=110u GAMMA=0.40 LAMBDA=0.04
  PMOS: VTO=-0.7 KP=50u  GAMMA=0.57 LAMBDA=0.05"""


@dataclass(frozen=True)
class Metric:
    """
    One measured characteristic and how it turns into a requirement.

    direction:
        "min"  - bigger is better, the spec reads "at least"   (gain, PM)
        "max"  - smaller is better, the spec reads "at most"   (power, TC)
        "eq"   - the value has to land on a given number       (vref, vout)

    "eq" is what the two-stage OTA never needed. A reference voltage or a
    hysteresis width is never "the bigger the better": 1.2 V means exactly
    1.2 V. So scoring for "eq" is symmetric, and the pass threshold is set
    by tol (achieved over target, 0.97 = +/-3%).
    """
    name: str
    direction: str
    unit: str
    label: str                       # human-readable name for the prompt
    sanity: Tuple[float, float]      # outside this range the circuit is dull
    tol: float = 0.97                # "eq" only
    eq_sig: int = 3                  # significant digits of an "eq" target
    cap: Optional[float] = None      # target ceiling for "min" (PM: 70 deg)
    fmt: str = "{:.4g}"

    @property
    def op(self):
        return {"min": ">=", "max": "<=", "eq": "=="}[self.direction]

    def show(self, value):
        return self.fmt.format(value)


@dataclass(frozen=True)
class Circuit:
    """The full topology: how to simulate it, what to measure, how to show it."""
    name: str
    title: str                       # human name ("two-stage Miller OTA")
    summary: str                     # one line: what skill this is about
    netlist: str                     # the .sp template with {PARAMETERS}
    param_names: Tuple[str, ...]
    bounds: dict
    reference: dict                  # a known working operating point
    metrics: Tuple[Metric, ...]
    outputs: Tuple[Tuple[str, int], ...]   # (file, how many numbers) from ngspice
    parse: Callable                  # dict[file -> list[float]] -> measured|None
    skeleton: str                    # netlist for the prompt (with {PARAMETERS})
    models_block: str                # models and conditions for the prompt
    hint: str = ""                   # a physics hint shown in the prompt
    timeout: float = 20.0

    @property
    def fingerprint(self):
        """
        Circuit fingerprint: netlist + bounds + reference + metrics.

        Tasks are generated FROM THE SOLUTION, so a task's targets are
        derived from one specific netlist. Change the .sp or the bounds
        later and an old tasks.json goes stale in silence: the stored
        reference no longer produces the measurements its own targets were
        made from, and the reference baseline drops below 100% - which
        looks like a broken generator when in fact only the pair
        "dataset + circuit" has drifted apart. The fingerprint makes that
        visible immediately.
        """
        blob = "|".join([
            self.netlist,
            repr(sorted(self.bounds.items())),
            repr(sorted(self.reference.items())),
            repr([(m.name, m.direction, m.sanity, m.tol, m.eq_sig, m.cap)
                  for m in self.metrics]),
        ])
        return hashlib.sha1(blob.encode()).hexdigest()[:12]

    @property
    def metric_names(self):
        return tuple(m.name for m in self.metrics)

    def metric(self, name):
        for m in self.metrics:
            if m.name == name:
                return m
        raise KeyError(name)

    def render(self, template, params, fmt="{:.6e}"):
        """Substitutes parameter values into any template of this circuit."""
        text = template
        for name in self.param_names:
            text = text.replace("{" + name + "}",
                                fmt.format(float(params[name])))
        return text

    def render_netlist(self, params):
        return self.render(self.netlist, params)

    def render_skeleton(self, params):
        return self.render(self.skeleton, params, fmt="{:.4g}")

    def bounds_block(self):
        return "\n".join(f"  {k}: [{self.bounds[k][0]:.4g}, "
                         f"{self.bounds[k][1]:.4g}]" for k in self.param_names)

    def spec_block(self, targets, indent="  "):
        w = max(len(m.label) for m in self.metrics)
        lines = []
        for m in self.metrics:
            note = (f"  (within +/-{(1.0 - m.tol) * 100:.0f}%)"
                    if m.direction == "eq" else "")
            lines.append(f"{indent}{m.label:<{w}} {m.op} "
                         f"{m.show(targets[m.name])} {m.unit}{note}")
        return "\n".join(lines)

    def keys_block(self):
        return "{" + ", ".join(f'"{k}": <float>'
                               for k in self.param_names) + "}"

    def metric_keys_block(self):
        return "{" + ", ".join(f'"{m.name}": <float>'
                               for m in self.metrics) + "}"

    def metric_legend(self, indent="  "):
        w = max(len(m.name) for m in self.metrics)
        return "\n".join(f"{indent}{m.name:<{w}}  - {m.label}, {m.unit}"
                         for m in self.metrics)

    def measured_block(self, measured, indent="  "):
        w = max(len(m.label) for m in self.metrics)
        return "\n".join(f"{indent}{m.label:<{w}} = {m.show(measured[m.name])} "
                         f"{m.unit}" for m in self.metrics)
