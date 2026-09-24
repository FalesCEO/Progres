"""
Comparator with hysteresis.

The first circuit in the project that neither AC nor DC analysis can
score: both headline requirements are dynamic. The hysteresis width is
read off a slow input triangle (two trip points, one going up and one
coming down), the propagation delay off a sharp edge in the very same
transient run. This is the project's first step into the time domain.

The hysteresis is created by the cross-coupled pair M6/M7: while its
ratio to the diode-connected M3/M4 stays below one there is no positive
feedback and the hysteresis collapses to zero (such candidates are thrown
out by the sanity filter).
"""

from .base import MOS_MODELS_PROMPT, Circuit, Metric, load_netlist

PARAM_NAMES = ("W1", "L1", "W3", "L3", "W5", "L5",
               "W6", "L6", "W8", "L8", "W9", "L9", "Ib")

BOUNDS = {
    "W1": (2e-6, 200e-6), "L1": (0.5e-6, 5e-6),
    "W3": (2e-6, 200e-6), "L3": (0.5e-6, 5e-6),
    "W5": (2e-6, 200e-6), "L5": (0.5e-6, 5e-6),
    "W6": (2e-6, 400e-6), "L6": (0.5e-6, 5e-6),
    "W8": (2e-6, 400e-6), "L8": (0.5e-6, 5e-6),
    "W9": (2e-6, 400e-6), "L9": (0.5e-6, 5e-6),
    "Ib": (2e-6, 300e-6),
}

REFERENCE = {
    "W1": 20e-6, "L1": 1e-6,
    "W3": 10e-6, "L3": 1e-6,
    "W5": 20e-6, "L5": 1e-6,
    "W6": 25e-6, "L6": 1e-6,
    "W8": 30e-6, "L8": 1e-6,
    "W9": 30e-6, "L9": 1e-6,
    "Ib": 20e-6,
}

SKELETON = """M1 n1 inp tail 0 NMOS W={W1} L={L1}    ; input pair (inn = 1.2 V ref)
M2 n2 inn tail 0 NMOS W={W1} L={L1}
M3 n1 n1 vdd vdd PMOS W={W3} L={L3}    ; diode-connected load
M4 n2 n2 vdd vdd PMOS W={W3} L={L3}
M6 n1 n2 vdd vdd PMOS W={W6} L={L6}    ; cross-coupled pair -> hysteresis
M7 n2 n1 vdd vdd PMOS W={W6} L={L6}
M5 tail  nbias 0 0 NMOS W={W5} L={L5}  ; tail source
M9 nbias nbias 0 0 NMOS W={W5} L={L5}  ; bias mirror
Ibs vdd nbias {Ib}
M8  o1 n2     vdd vdd PMOS W={W8} L={L8}   ; gain stage
M10 o1 nbias  0   0   NMOS W={W9} L={L9}
M11 out o1 vdd vdd PMOS W=20u L=1u     ; output inverter (fixed)
M12 out o1 0   0   NMOS W=8u  L=1u
CLc out 0 0.2p"""

MODELS = MOS_MODELS_PROMPT + """
Supply 3.3 V, reference input v(inn) = 1.2 V, load CLc = 0.2 pF.
Stimulus: a 0.6 -> 1.8 -> 0.6 V triangle over 20 us (trip points), then a
1 ns full-swing edge (propagation delay), all in one transient run.
Trip points are read where v(out) crosses 1.65 V."""


def parse(files):
    """power.txt -> [P]; cmp.txt -> [Vth, Vtl, tprop]."""
    vth, vtl, tpr = files["cmp.txt"]
    pwr = files["power.txt"][0]
    hyst = vth - vtl
    # without positive feedback there is no hysteresis (or it goes negative)
    if hyst <= 0 or tpr <= 0 or pwr <= 0:
        return None
    return {"vhyst_v": hyst, "vtrip_v": 0.5 * (vth + vtl),
            "tprop_s": tpr, "power_w": pwr}


CIRCUIT = Circuit(
    name="comparator",
    title="comparator with hysteresis",
    summary="switching dynamics: hysteresis and delay in the time domain",
    netlist=load_netlist("comparator.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        Metric("vhyst_v", "eq", "V", "Hysteresis width", (3e-3, 0.5),
               tol=0.85, eq_sig=2),
        Metric("vtrip_v", "eq", "V", "Trip point centre", (0.75, 1.65),
               tol=0.97, eq_sig=3),
        Metric("tprop_s", "max", "s", "Propagation delay", (1e-10, 5e-6)),
        Metric("power_w", "max", "W", "Total power", (1e-6, 5e-2)),
    ),
    outputs=(("power.txt", 1), ("cmp.txt", 3)),
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="Hysteresis needs (W6/L6)/(W3/L3) > 1; the width grows with that "
         "ratio and with the tail current. Delay is set by the tail current "
         "charging the load at n1/n2 and o1.",
)
