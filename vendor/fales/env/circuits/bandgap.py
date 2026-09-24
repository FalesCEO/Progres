"""
Bandgap voltage reference (Kuijk cell).

A qualitatively different skill, not just "more transistors". There is no
gain and no bandwidth here: the headline requirement is temperature
stability. Vbe falls with temperature (CTAT, about -1.7 mV/K) while the
delta-Vbe of two transistors of different area rises (PTAT, VT*ln(N) with
a slope of +86 uV/K per unit of ln). The goal is to pick the resistor and
area ratios so that the two slopes cancel. This is a problem about
balancing derivatives, not about maximising a number.

The amplifier is an ideal E source: it holds v(na)=v(nb) and is not part
of the problem. What has to be designed is the reference core itself.
"""

from .base import Circuit, Metric, load_netlist

PARAM_NAMES = ("R1", "R2", "R3", "A1", "A2")

BOUNDS = {
    "R1": (1e3, 500e3),
    "R2": (1e3, 500e3),
    "R3": (200.0, 100e3),
    "A1": (1.0, 20.0),
    "A2": (1.0, 40.0),
}

REFERENCE = {"R1": 20e3, "R2": 20e3, "R3": 2e3, "A1": 1.0, "A2": 8.0}

SKELETON = """Eop vref 0 na nb 1e5      ; ideal amp forces v(na) = v(nb)
R1 vref na {R1}           ; ctat branch
Q1 na na 0 0 QN area={A1}
R2 vref nb {R2}           ; ptat branch
R3 nb nc {R3}
Q2 nc nc 0 0 QN area={A2}"""

MODELS = """Model: .model QN NPN (IS=1e-17 BF=150 VAF=60 RB=10 RE=1)
Supply 3.3 V. Both transistors are diode-connected to ground.
Vbe = VT*ln(Ic/(IS*area)), VT = kT/q = 25.85 mV at 27 C.
Temperature is swept -40 C .. +125 C; the reference is read at 27 C."""


def parse(files):
    """power.txt -> [P]; bg.txt -> [vref@27C, TC in ppm/C]."""
    vref, tc = files["bg.txt"]
    pwr = files["power.txt"][0]
    if vref <= 0 or pwr <= 0 or tc < 0:
        return None
    return {"vref_v": vref, "tc_ppm": tc, "power_w": pwr}


CIRCUIT = Circuit(
    name="bandgap",
    title="bandgap voltage reference (Kuijk cell)",
    summary="temperature stability: balancing PTAT against CTAT, not gain",
    netlist=load_netlist("bandgap.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        # a reference voltage is an "exactly this" spec, not "at least this"
        Metric("vref_v", "eq", "V", "Reference voltage", (0.5, 2.5),
               tol=0.97, eq_sig=3, fmt="{:.4g}"),
        Metric("tc_ppm", "max", "ppm/C", "Temperature coeff", (2.0, 3000.0)),
        Metric("power_w", "max", "W", "Total power", (1e-7, 1e-2)),
    ),
    outputs=(("power.txt", 1), ("bg.txt", 2)),
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="v(na)=v(nb) gives I2*R3 = VT*ln(A2*R2/(A1*R1)) and "
         "vref = Vbe1 + (R2/R3)*VT*ln(A2*R2/(A1*R1)). Zero TC needs the "
         "PTAT slope (+86 uV/K per unit ln) to cancel dVbe/dT (-1.7 mV/K). "
         "tc_ppm = 1e6*(Vmax-Vmin)/(Vref27*165).",
)
