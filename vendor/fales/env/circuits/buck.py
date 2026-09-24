"""
Buck converter (asynchronous, fixed 1 MHz switching).

A new axis: energy. Every circuit so far was scored on what it does to a
signal; this one is scored on what it does to power. Efficiency is not a
small-signal quantity and cannot be read off an AC sweep - it is the
ratio of two averaged products over a switching cycle, so it only exists
in the time domain, and only after the converter has settled.

The design is genuinely over-constrained, which is the point:

  * a larger L cuts the inductor ripple current and therefore the output
    ripple - and stores more energy, so the output sags further and for
    longer when the load steps;
  * a larger Cout cuts both the ripple and the droop - and slows the
    settling, so the converter needs longer to reach the steady state
    the measurement window assumes;
  * the ESR of that capacitor puts a floor under the ripple no matter how
    large the capacitance is, because the inductor ripple current flows
    through it;
  * a lower switch resistance lifts the efficiency and costs area, while
    the diode's forward drop is a loss that grows with load current and
    cannot be designed away at all in this topology;
  * the on-time sets the output voltage, and every one of the above is
    measured at whatever voltage it produces.

There is no feedback loop here. That is deliberate: the droop is then a
property of the power stage itself - the transient undershoot of an
underdamped LC into a doubled load - and not a measurement of some
compensator that would have to be designed as well.
"""

from .base import Circuit, Metric, load_netlist

PARAM_NAMES = ("Ton", "L", "Cout", "Resr", "Ron")

BOUNDS = {
    "Ton": (0.05e-6, 0.9e-6),
    "L": (1e-6, 200e-6),
    "Cout": (0.1e-6, 100e-6),
    "Resr": (1e-3, 1.0),
    "Ron": (0.02, 2.0),
}

REFERENCE = {"Ton": 400e-9, "L": 10e-6, "Cout": 1e-6,
             "Resr": 0.05, "Ron": 0.15}

SKELETON = """Vpwm pwm 0 PULSE(0 5 0 2n 2n {Ton} 1u)  ; D = Ton / 1 us
.model SWM SW(RON={Ron} ROFF=1meg VT=2.5 VH=0.1)
S1 vin sw pwm 0 SWM            ; high-side switch, vin = 5 V
D1 0 sw DSCH                   ; freewheeling diode
L1 sw out {L}
Cout out oe {Cout}
Resr oe 0 {Resr}               ; ESR: a floor under the ripple
Rload out 0 5                  ; 5 ohm nominal load
S2 out ld stp 0 SWL            ; a second 5 ohm load switches in at 100 us
Rld2 ld 0 5"""

MODELS = """Input 5 V, switching period fixed at 1 us (1 MHz), nominal load
5 ohm. Diode: .model DSCH D(IS=1e-6 N=1.0 RS=0.01 CJO=100p).
One 140 us transient run. The steady state is averaged over 80..100 us,
just before a load step that doubles the load at 100 us:
  vout   = average output over 80..100 us
  ripple = peak-to-peak output over the same window
  eff    = 100 * avg(Vout^2/5) / avg(5 V * Iin) over the same window
  droop  = vout - min(output) over 100..130 us"""


def parse(files):
    """buck.txt -> [Vss, Vpp, Pin, Pout, Vmin]."""
    vss, vpp, pin, pout, vmn = files["buck.txt"]
    # a converter that delivers nothing, draws nothing, or shows no ripple
    # at all has not actually run
    if vss <= 0 or pin <= 0 or pout <= 0 or vpp <= 0:
        return None
    droop = vss - vmn
    # the load can only pull the output down; a negative droop means the
    # measurement window caught something other than the step response
    if droop <= 0:
        return None
    return {
        "vout_v": vss,
        "ripple_v": vpp,
        "eff_pct": 100.0 * pout / pin,
        "droop_v": droop,
    }


CIRCUIT = Circuit(
    name="buck",
    title="buck converter (asynchronous, 1 MHz)",
    summary="energy: efficiency, ripple and load-step droop at once",
    netlist=load_netlist("buck.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        Metric("vout_v", "eq", "V", "Output voltage", (0.3, 4.5),
               tol=0.97, eq_sig=3),
        Metric("ripple_v", "max", "V", "Output ripple pp", (1e-4, 1.0)),
        Metric("eff_pct", "min", "%", "Efficiency", (30.0, 99.5)),
        Metric("droop_v", "max", "V", "Load-step droop", (1e-3, 2.0)),
    ),
    outputs=(("buck.txt", 5),),
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="Vout = D*Vin minus the diode drop and the IR losses, with "
         "D = Ton/1us. Inductor ripple current is (Vin-Vout)*D*T/L, and the "
         "output ripple is that current split between 1/(8*fsw*Cout) and "
         "Resr. The droop is the undershoot of an LC with damping "
         "(1/(2*Rload))*sqrt(L/Cout), so more L makes it worse and more "
         "Cout makes it better.",
)
