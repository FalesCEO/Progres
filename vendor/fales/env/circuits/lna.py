"""
Low-noise amplifier (common source with source degeneration).

A new axis: noise. Every circuit so far could be scored from gain,
timing or a DC level; here the quantity that matters is the one the
circuit itself generates. ngspice computes it with a real `.noise`
analysis, and the number is referred back to the input, which is what an
RF or sensor front end is actually specified on.

The trade-off is genuinely three-cornered and none of the corners can be
won for free:

  * more gm (a wider device, or more current) lowers the input-referred
    noise and raises the gain - and costs power directly;
  * a larger RD raises the gain and pushes the load resistor's own noise
    contribution down when referred to the input - and moves the output
    pole down with it, so the bandwidth falls;
  * source degeneration Rs linearises the stage but both cuts the gain
    and adds its own thermal noise, so it is never free.

The noise is integrated over a FIXED 1 kHz .. 1 MHz band. That is
deliberate: integrating past the -3 dB corner would let the referred
noise diverge exactly where the gain rolls off, and vn_in would end up
re-measuring the bandwidth instead of the noise.
"""

from .base import Circuit, Metric, load_netlist

PARAM_NAMES = ("W1", "L1", "RD", "Rs", "Vg")

BOUNDS = {
    "W1": (5e-6, 500e-6), "L1": (0.5e-6, 5e-6),
    "RD": (200.0, 50e3),
    "Rs": (1.0, 5e3),
    "Vg": (0.9, 2.2),
}

REFERENCE = {"W1": 100e-6, "L1": 1e-6, "RD": 2e3, "Rs": 100.0, "Vg": 1.2}

SKELETON = """Vg gate 0 DC {Vg} AC 1        ; bias, ac drive and noise reference
M1 out gate src 0 NMOS W={W1} L={L1}
Rs src 0 {Rs}                 ; degeneration
RD vdd out {RD}               ; load: gain with gm, pole with CL
CL out 0 1p"""

MODELS = """Model: LEVEL=1 NMOS, VTO=0.7 KP=110u GAMMA=0.40 LAMBDA=0.04.
Supply 3.3 V, fixed load CL = 1 pF. The stage self-biases: Vgs settles at
Vg - Id*Rs, so Vg and Rs together set the operating current.
Gain is read at 10 kHz, bandwidth is the -3 dB corner above it.
Noise is the input-referred voltage integrated over a fixed 1 kHz .. 1 MHz
band, in volts rms."""


def parse(files):
    """power.txt -> [P]; ac.txt -> [gain_db, bw]; noise.txt -> [vn_in]."""
    pwr = files["power.txt"][0]
    g0, bw = files["ac.txt"]
    vn = files["noise.txt"][0]
    # a stage that draws nothing is off; zero bandwidth or zero noise
    # means the analysis produced no usable operating point
    if pwr <= 0 or bw <= 0 or vn <= 0:
        return None
    return {"vn_in": vn, "gain_db": g0, "bw_hz": bw, "power_w": pwr}


CIRCUIT = Circuit(
    name="lna",
    title="low-noise amplifier (degenerated common source)",
    summary="noise: input-referred noise traded against bandwidth and power",
    netlist=load_netlist("lna.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        Metric("vn_in", "max", "V", "Input noise (1k-1M)", (1e-7, 1e-4)),
        Metric("gain_db", "min", "dB", "Gain at 10 kHz", (5.0, 45.0)),
        Metric("bw_hz", "min", "Hz", "-3 dB bandwidth", (2e6, 2e9)),
        Metric("power_w", "max", "W", "Total power", (1e-5, 5e-2)),
    ),
    outputs=(("power.txt", 1), ("ac.txt", 2), ("noise.txt", 1)),
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="Gain = gm*RD/(1 + gm*Rs), bandwidth = 1/(2*pi*(RD||ro)*CL). The "
         "input-referred noise is dominated by the channel term 4kT*(2/3)/gm "
         "plus RD's 4kT*RD/(gm*RD)^2 and Rs's own 4kT*Rs, so raising gm helps "
         "twice while raising Rs hurts twice.",
)
