"""
Low-dropout regulator (LDO).

Another qualitatively different skill: stability of the feedback loop
under load, and power supply rejection (PSRR). This is the first circuit
with an explicit loop - it is broken at AC by a 1 GH inductor (a short at
DC, an open at AC) and driven through a 1 GF capacitor. After the loop
gain has been measured the loop is closed again (alter) and the same AC
analysis is repeated with the drive moved to the supply rail - that is
how PSRR is measured.

The central conflict of the task: raising Cc buys phase margin but drags
the loop unity-gain frequency down and hurts PSRR; the zero from the
output capacitor ESR rescues the phase, but you pay for it in ripple.
"""

from .base import Circuit, Metric, load_netlist

PARAM_NAMES = ("Wp", "Lp", "R1", "R2", "Gm", "Ro", "Cc", "Cout", "Resr")

BOUNDS = {
    "Wp": (100e-6, 5000e-6), "Lp": (0.5e-6, 3e-6),
    "R1": (10e3, 2e6), "R2": (10e3, 2e6),
    "Gm": (1e-6, 1e-3), "Ro": (100e3, 50e6),
    "Cc": (0.1e-12, 200e-12),
    "Cout": (0.1e-6, 10e-6), "Resr": (0.01, 20.0),
}

REFERENCE = {
    "Wp": 2000e-6, "Lp": 1e-6,
    "R1": 100e3, "R2": 100e3,
    "Gm": 100e-6, "Ro": 2e6,
    "Cc": 5e-12, "Cout": 1e-6, "Resr": 2.0,
}

SKELETON = """Gea ea 0 ref fbin {Gm}          ; error amp: I = Gm*(v(ref)-v(fbin))
Roa vdd ea {Ro}                 ; amp output resistance, gain = Gm*Ro
Cc ea 0 {Cc}                    ; dominant-pole compensation
Mp out ea vdd vdd PMOS W={Wp} L={Lp}   ; pass device
R1 out fb {R1}                  ; feedback divider
R2 fb 0 {R2}
Cout out oe {Cout}              ; output cap ...
Resr oe 0 {Resr}                ; ... and its ESR (creates a zero)
Iload out 0 10m                 ; fixed load
Lb fb fbin 1G                   ; ac loop break (dc short)
Vinj inj 0 AC 1
Cinj inj fbin 1G                ; ac injection into the broken node"""

MODELS = """Model: LEVEL=1 PMOS, VTO=-0.7 KP=50u GAMMA=0.57 LAMBDA=0.05.
Supply 3.3 V, internal reference v(ref) = 1.2 V, load current fixed at 10 mA.
Loop gain is measured as -v(fb) with v(fbin) driven; phase margin is taken
at its unity-gain crossing. PSRR is measured with the loop closed, ac drive
moved to Vdd, at 1 kHz, reported as a positive number of dB."""


def parse(files):
    """dc.txt -> [Vout, Iq]; ac.txt -> [T0, ugf, phugf, phdc]; psrr.txt -> [dB]."""
    vout, iq = files["dc.txt"]
    tdc, ugf, phugf, phdc = files["ac.txt"]
    psrr = files["psrr.txt"][0]
    if vout <= 0 or iq <= 0 or ugf <= 0:
        return None
    pm = 180.0 + (phugf - phdc)
    while pm > 360.0:
        pm -= 360.0
    while pm < -180.0:
        pm += 360.0
    # a loop with negative DC gain does not regulate at all
    if tdc <= 0:
        return None
    return {"vout_v": vout, "pm_deg": pm, "psrr_db": -psrr, "iq_a": iq}


CIRCUIT = Circuit(
    name="ldo",
    title="low-dropout regulator (PMOS pass device)",
    summary="loop stability under load and supply noise rejection",
    netlist=load_netlist("ldo.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        Metric("vout_v", "eq", "V", "Output voltage", (1.3, 3.0),
               tol=0.97, eq_sig=3),
        Metric("pm_deg", "min", "deg", "Loop phase margin", (5.0, 120.0),
               cap=70.0),
        Metric("psrr_db", "min", "dB", "PSRR at 1 kHz", (15.0, 110.0)),
        Metric("iq_a", "max", "A", "Quiescent current", (1e-7, 5e-3)),
    ),
    outputs=(("dc.txt", 2), ("ac.txt", 4), ("psrr.txt", 1)),
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="Vout = 1.2*(1 + R1/R2). The dominant pole sits at the amp output "
         "(Ro, Cc + Cgs of the pass device), the second pole at the load "
         "node; the ESR zero at 1/(2*pi*Cout*Resr) buys phase back.",
)
