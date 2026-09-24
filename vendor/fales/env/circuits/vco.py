"""
Voltage-controlled oscillator (three-stage current-starved ring).

A new axis: the periodic steady state. Every circuit before this one had
an operating point to linearise around - here there is none. A ring
oscillator has no stable DC solution at all: the only solution ngspice
can find by itself is the unstable one in the middle, so every run starts
from an initial condition and runs open-loop in time (`uic`). What is
being scored is a property of the limit cycle, not of a bias point.

The second thing that is new: two of the metrics are not measurable in a
single run. Tuning gain is a derivative, and supply pushing is a
sensitivity, so the netlist runs the transient three times - nominal,
control stepped by +200 mV, supply stepped by +200 mV - and parse()
turns the three frequencies into the two slopes. The control voltage is
split across two series sources so the step can be applied by altering a
source, without arithmetic inside the netlist.

The trade-off is the one every VCO designer knows and cannot escape:

  * starving the stages harder (a narrower Ws, a lower Vc) buys a lower
    frequency and less power, but the stage delay becomes dominated by a
    weak current into the load cap, which makes the frequency far more
    sensitive to everything - including the supply, which is exactly what
    `pushing` measures;
  * a wide tuning gain kvco makes the oscillator easy to lock in a PLL
    but multiplies any noise on the control line straight into jitter;
  * more current per stage cuts the pushing and steadies the frequency,
    and is paid for directly in power.

Starve too hard and the ring simply stops oscillating - the measurement
finds no edges, parse() returns None, and the candidate is dropped.
"""

from .base import MOS_MODELS_PROMPT, Circuit, Metric, load_netlist

PARAM_NAMES = ("Wp", "Wn", "Ws", "L", "Cl", "Vc")

BOUNDS = {
    "Wp": (5e-6, 200e-6),
    "Wn": (2e-6, 100e-6),
    "Ws": (1e-6, 50e-6),
    "L": (0.5e-6, 5e-6),
    "Cl": (10e-15, 2e-12),
    "Vc": (0.9, 2.5),
}

REFERENCE = {"Wp": 40e-6, "Wn": 20e-6, "Ws": 6e-6,
             "L": 2e-6, "Cl": 200e-15, "Vc": 1.5}

SKELETON = """Vctrl ctrl cx {Vc}                     ; control voltage
Vdelta cx 0 0                          ; stepped +200 mV for the kvco run
.ic v(n1)=0 v(n2)=3.3 v(n3)=0          ; a ring has no stable dc point
Mp1 n1 n3 vdd vdd PMOS W={Wp} L={L}    ; stage 1
Mn1 n1 n3 s1 0 NMOS W={Wn} L={L}
Ms1 s1 ctrl 0 0 NMOS W={Ws} L={L}      ; starving device sets the delay
C1 n1 0 {Cl}
Mp2 n2 n1 vdd vdd PMOS W={Wp} L={L}    ; stage 2 (same, n1 -> n2)
Mn2 n2 n1 s2 0 NMOS W={Wn} L={L}
Ms2 s2 ctrl 0 0 NMOS W={Ws} L={L}
C2 n2 0 {Cl}
Mp3 n3 n2 vdd vdd PMOS W={Wp} L={L}    ; stage 3 (same, n2 -> n3)
Mn3 n3 n2 s3 0 NMOS W={Wn} L={L}
Ms3 s3 ctrl 0 0 NMOS W={Ws} L={L}
C3 n3 0 {Cl}"""

MODELS = MOS_MODELS_PROMPT + """
Supply 3.3 V nominal. Three transient runs of 500 ns each, all started
from the initial condition with uic:
  1. nominal Vc and 3.3 V supply  -> fosc and the average supply power
  2. Vc + 200 mV                  -> kvco  = (f2 - f1) / 0.2 V
  3. supply 3.5 V, Vc nominal     -> pushing = |f3 - f1| / 0.2 V
The frequency is taken from five periods between the 3rd and the 8th
rising crossing of 1.65 V on n1, so the start-up transient is skipped."""


def parse(files):
    """
    f0.txt -> [fosc, P]; f1.txt -> [f at Vc+0.2]; f2.txt -> [f at Vdd+0.2].

    The two slopes are formed here rather than in the netlist: ngspice
    opens a fresh plot for every transient run, so the frequencies cannot
    be held side by side inside the .control block.
    """
    fosc, pwr = files["f0.txt"]
    f_ctrl = files["f1.txt"][0]
    f_vdd = files["f2.txt"][0]
    # no oscillation, or an unusable measurement, means no result at all
    if fosc <= 0 or f_ctrl <= 0 or f_vdd <= 0 or pwr <= 0:
        return None
    return {
        "fosc_hz": fosc,
        # a negative tuning gain (frequency falling with control voltage)
        # is a real, and bad, design outcome - it is left in and the
        # sanity range rejects it
        "kvco": (f_ctrl - fosc) / 0.2,
        "pushing": abs(f_vdd - fosc) / 0.2,
        "power_w": pwr,
    }


CIRCUIT = Circuit(
    name="vco",
    title="voltage-controlled ring oscillator",
    summary="periodic steady state: tuning gain and supply pushing",
    netlist=load_netlist("vco.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        Metric("fosc_hz", "eq", "Hz", "Oscillation freq", (5e6, 1e9),
               tol=0.97, eq_sig=3),
        Metric("kvco", "eq", "Hz/V", "Tuning gain", (1e6, 2e9),
               tol=0.85, eq_sig=2),
        Metric("pushing", "max", "Hz/V", "Supply pushing", (1e4, 5e8)),
        Metric("power_w", "max", "W", "Total power", (1e-4, 2e-1)),
    ),
    outputs=(("f0.txt", 2), ("f1.txt", 1), ("f2.txt", 1)),
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="Frequency is 1/(2*N*td) with N=3 stages, and the stage delay td "
         "is roughly Cl*Vdd/(2*Istarve), so fosc rises with the starving "
         "current and falls with Cl. Everything that makes the delay depend "
         "on the starving current alone also makes it depend on the supply, "
         "so a large kvco and a small pushing pull against each other.",
)
