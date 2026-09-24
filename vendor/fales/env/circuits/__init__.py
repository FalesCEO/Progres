"""
Circuit registry.

The order in CIRCUITS is the order of increasing difficulty: from the
five-transistor amplifier to the comparator with its time-domain specs.
The same order is used as the default in the generator and in every
report, so the difficulty progression is visible at a glance.
"""

from . import (bandgap, buck, buffer, comparator, diffamp, ldo, lna,
               mod1, ota, vco)
from .base import Circuit, Metric

CIRCUITS = {c.name: c for c in (
    diffamp.CIRCUIT,     # simplest: 7 parameters, one stage
    ota.CIRCUIT,         # canonical: 13 parameters, Miller compensation
    bandgap.CIRCUIT,     # other skill: temperature stability
    ldo.CIRCUIT,         # other skill: loop stability + PSRR
    comparator.CIRCUIT,  # other skill: time domain
    lna.CIRCUIT,         # other skill: noise
    buffer.CIRCUIT,      # other skill: large-signal linearity
    vco.CIRCUIT,         # other skill: periodic steady state
    buck.CIRCUIT,        # other skill: energy and efficiency
    mod1.CIRCUIT,        # other skill: whole-system conversion
)}

NAMES = tuple(CIRCUITS)
DEFAULT = "ota"          # tasks with no "circuit" field are old OTA tasks


def stamp():
    """Fingerprints of every circuit - stored in tasks.json under "circuits"."""
    return {name: c.fingerprint for name, c in CIRCUITS.items()}


def check_stamp(saved):
    """
    Compares a dataset fingerprint against the current circuits.

    Returns the names of the circuits that drifted. An empty list means
    either "everything matches" or "the file carries no fingerprint"
    (older datasets - we leave them alone and simply claim nothing).
    """
    if not isinstance(saved, dict) or not saved:
        return []
    now = stamp()
    return sorted(n for n, fp in saved.items()
                  if n in now and now[n] != fp)


def get(name=None):
    name = name or DEFAULT
    if name not in CIRCUITS:
        raise KeyError(f"unknown circuit: {name}. Available: {', '.join(NAMES)}")
    return CIRCUITS[name]


__all__ = ["CIRCUITS", "NAMES", "DEFAULT", "Circuit", "Metric",
           "get", "stamp", "check_stamp"]
