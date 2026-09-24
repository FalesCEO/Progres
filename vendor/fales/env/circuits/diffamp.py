"""
Single-stage differential amplifier (5-transistor OTA).

Deliberately simpler than the Miller OTA: seven parameters instead of
thirteen, a single high-impedance node, no compensation at all. It exists
so the dataset has a low end to its difficulty scale - without one it is
impossible to tell "the model can design" from "the tasks are too hard
for everybody".
"""

from .base import MOS_MODELS_PROMPT, Circuit, Metric, load_netlist
from .ota import parse

PARAM_NAMES = ("W1", "L1", "W3", "L3", "W5", "L5", "Ib")

BOUNDS = {
    "W1": (2e-6, 200e-6), "L1": (0.5e-6, 5e-6),
    "W3": (2e-6, 200e-6), "L3": (0.5e-6, 5e-6),
    "W5": (2e-6, 200e-6), "L5": (0.5e-6, 5e-6),
    "Ib": (2e-6, 300e-6),
}

REFERENCE = {
    "W1": 20e-6, "L1": 1e-6,
    "W3": 10e-6, "L3": 1e-6,
    "W5": 20e-6, "L5": 1e-6,
    "Ib": 20e-6,
}

SKELETON = """M1 n1  inp tail 0   NMOS W={W1} L={L1}   ; input pair
M2 out inn tail 0   NMOS W={W1} L={L1}
M3 n1  n1  vdd vdd  PMOS W={W3} L={L3}   ; pmos mirror load
M4 out n1  vdd vdd  PMOS W={W3} L={L3}
M5 tail  nbias 0 0  NMOS W={W5} L={L5}   ; tail source
M8 nbias nbias 0 0  NMOS W={W5} L={L5}   ; bias mirror
Ibs vdd nbias {Ib}
CL out 0 2p"""

MODELS = MOS_MODELS_PROMPT + """
Supply 3.3 V, input common mode 1.2 V, load CL = 2 pF."""


CIRCUIT = Circuit(
    name="diffamp",
    title="single-stage 5-transistor differential amplifier",
    summary="sizing on easy mode: the same four specs, only 7 parameters",
    netlist=load_netlist("diffamp.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        Metric("gain_db", "min", "dB", "DC gain", (10.0, 70.0)),
        Metric("gbw_hz", "min", "Hz", "Unity-gain BW", (1e5, 5e8)),
        Metric("pm_deg", "min", "deg", "Phase margin", (15.0, 130.0), cap=70.0),
        Metric("power_w", "max", "W", "Total power", (1e-6, 5e-2)),
    ),
    outputs=(("power.txt", 1), ("ac.txt", 4)),
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="Single high-impedance node (out): gain = gm1*(ro2||ro4), "
         "GBW = gm1/(2*pi*CL).",
)
