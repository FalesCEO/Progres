"""Two-stage Miller OTA - the canonical example of the project (baseline)."""

from .base import MOS_MODELS_PROMPT, Circuit, Metric, load_netlist

PARAM_NAMES = ("W1", "L1", "W3", "L3", "W5", "L5",
               "W6", "L6", "W7", "L7", "Cc", "Rz", "Ib")

BOUNDS = {
    "W1": (2e-6, 200e-6), "L1": (0.5e-6, 5e-6),
    "W3": (2e-6, 200e-6), "L3": (0.5e-6, 5e-6),
    "W5": (2e-6, 200e-6), "L5": (0.5e-6, 5e-6),
    "W6": (2e-6, 400e-6), "L6": (0.5e-6, 5e-6),
    "W7": (2e-6, 400e-6), "L7": (0.5e-6, 5e-6),
    "Cc": (0.1e-12, 20e-12),
    "Rz": (100.0, 50e3),
    "Ib": (2e-6, 300e-6),
}

REFERENCE = {
    "W1": 20e-6, "L1": 1e-6,
    "W3": 10e-6, "L3": 1e-6,
    "W5": 20e-6, "L5": 1e-6,
    "W6": 60e-6, "L6": 1e-6,
    "W7": 30e-6, "L7": 1e-6,
    "Cc": 1e-12, "Rz": 1e3, "Ib": 20e-6,
}

SKELETON = """M1 n1 inp tail 0 NMOS W={W1} L={L1}     ; input pair
M2 n2 inn tail 0 NMOS W={W1} L={L1}
M3 n1 n1 vdd vdd PMOS W={W3} L={L3}     ; pmos mirror load
M4 n2 n1 vdd vdd PMOS W={W3} L={L3}
M5 tail nbias 0 0 NMOS W={W5} L={L5}    ; tail source
M8 nbias nbias 0 0 NMOS W={W5} L={L5}   ; bias mirror
Ibs vdd nbias {Ib}
M6 out n2 vdd vdd PMOS W={W6} L={L6}    ; second stage
M7 out nbias 0 0 NMOS W={W7} L={L7}
Cc n2 outx {Cc}                          ; miller cap
Rz outx out {Rz}                         ; nulling resistor
CL out 0 2p"""

MODELS = MOS_MODELS_PROMPT + """
Supply 3.3 V, input common mode 1.2 V, load CL = 2 pF."""


def parse(files):
    """power.txt -> [P]; ac.txt -> [dcgain, ugf, phugf, phdc]."""
    dcgain, ugf, phugf, phdc = files["ac.txt"]
    pwr = files["power.txt"][0]
    if ugf <= 0 or pwr <= 0:
        return None
    # the phase is normalised against the DC phase, so the formula works
    # for both inverting and non-inverting topologies
    pm = 180.0 + (phugf - phdc)
    while pm > 360.0:
        pm -= 360.0
    while pm < -180.0:
        pm += 360.0
    return {"gain_db": dcgain, "gbw_hz": ugf, "pm_deg": pm, "power_w": pwr}


CIRCUIT = Circuit(
    name="ota",
    title="two-stage Miller-compensated OTA",
    summary="the classic sizing problem: gain / bandwidth / phase margin / power",
    netlist=load_netlist("ota.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        Metric("gain_db", "min", "dB", "DC gain", (15.0, 90.0), fmt="{:.4g}"),
        Metric("gbw_hz", "min", "Hz", "Unity-gain BW", (1e5, 5e8)),
        Metric("pm_deg", "min", "deg", "Phase margin", (15.0, 130.0), cap=70.0),
        Metric("power_w", "max", "W", "Total power", (1e-6, 5e-2)),
    ),
    outputs=(("power.txt", 1), ("ac.txt", 4)),
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="Miller compensation sets the dominant pole; Rz cancels the RHP zero.",
)
