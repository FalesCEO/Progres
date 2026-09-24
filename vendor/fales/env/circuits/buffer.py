"""
Voltage buffer (source follower) driving a resistive load.

A new axis: linearity. Everything scored so far was a small-signal or a
static number - a circuit could be perfectly linear or hopelessly bent
and neither gain nor phase margin would notice. Here the whole point is
how faithfully a large signal survives the trip through the stage, and
the number comes from the harmonics of a real transient run.

Where the distortion comes from is worth knowing, because it decides
which knob helps. A source follower has a signal-dependent Vgs: as the
output swings, the drain current through the tail device and the load
resistor changes, and the body effect (GAMMA) moves the threshold with
the source voltage. Both are even-order effects, so the residue is
dominated by the SECOND harmonic - which is exactly what the simulation
shows, h2 sitting an order of magnitude above h3.

The trade-off:

  * more tail current and a wider follower raise gm, so the fraction of
    the swing that lands across Vgs shrinks and the distortion falls -
    and the quiescent current is a scored metric, so linearity is paid
    for in power;
  * a heavier load (smaller RL) draws a larger signal current through
    the device, which both bends the transfer curve and eats the swing;
  * the common mode has to sit high enough for the tail device to stay
    in saturation across the whole swing, and low enough that the
    follower keeps headroom to the rail.

The harmonics are extracted by projecting the output onto sin/cos rather
than by an FFT: the record covers exactly two periods and `linearize`
makes the sampling uniform, so the projection is an exact quadrature
with no window and no zero padding.
"""

from .base import MOS_MODELS_PROMPT, Circuit, Metric, load_netlist

PARAM_NAMES = ("W1", "L1", "W2", "L2", "Ib", "RL", "Vcm")

BOUNDS = {
    "W1": (10e-6, 1000e-6), "L1": (0.5e-6, 5e-6),
    "W2": (5e-6, 400e-6), "L2": (0.5e-6, 5e-6),
    "Ib": (2e-6, 500e-6),
    "RL": (1e3, 500e3),
    "Vcm": (1.4, 2.8),
}

REFERENCE = {"W1": 200e-6, "L1": 1e-6, "W2": 60e-6, "L2": 1e-6,
             "Ib": 50e-6, "RL": 20e3, "Vcm": 2.0}

SKELETON = """Vin in 0 DC {Vcm} SIN({Vcm} 0.7 10k)   ; fixed 0.7 V, 10 kHz drive
M1 vdd in out 0 NMOS W={W1} L={L1}     ; follower
M2 out nbias 0 0 NMOS W={W2} L={L2}    ; tail current source
M3 nbias nbias 0 0 NMOS W={W2} L={L2}  ; bias mirror
Ibs vdd nbias {Ib}
RL out 0 {RL}                          ; load
CL out 0 5p"""

MODELS = MOS_MODELS_PROMPT + """
Supply 3.3 V, load capacitance 5 pF. The stimulus is fixed: a 0.7 V
amplitude sine at 10 kHz riding on Vcm, so the output swing is an outcome
of the design and not a knob.
THD is the root-sum-square of harmonics 2..5 over the fundamental, in
percent; swing is the peak-to-peak output; Iq is the quiescent supply
current at the operating point."""


def parse(files):
    """dc.txt -> [Iq]; thd.txt -> [THD %, swing, fundamental]."""
    iq = files["dc.txt"][0]
    thd, sw, h1 = files["thd.txt"]
    # h1 is the fundamental: if it collapsed the stage is not passing the
    # signal at all and THD is a ratio to nothing. A dead stage draws no
    # current and produces no swing.
    if iq <= 0 or thd < 0 or sw <= 0 or h1 <= 0:
        return None
    return {"thd_pct": thd, "swing_v": sw, "iq_a": iq}


CIRCUIT = Circuit(
    name="buffer",
    title="source-follower voltage buffer",
    summary="linearity: large-signal distortion traded against quiescent power",
    netlist=load_netlist("buffer.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        Metric("thd_pct", "max", "%", "THD (h2..h5)", (0.01, 30.0)),
        Metric("swing_v", "min", "V", "Output swing pp", (0.05, 3.0)),
        Metric("iq_a", "max", "A", "Quiescent current", (1e-6, 2e-2)),
    ),
    outputs=(("dc.txt", 1), ("thd.txt", 3)),
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="The follower gain is gm*(RL||ro)/(1 + (gm+gmb)*(RL||ro)), so the "
         "output tracks the input only as far as gm allows; whatever is left "
         "over lands across Vgs and comes back as distortion. Body effect "
         "makes it mostly second order. Raising Ib or W1 raises gm and cuts "
         "THD, at the cost of Iq.",
)
