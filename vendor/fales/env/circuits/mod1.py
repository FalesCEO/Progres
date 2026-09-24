"""
First-order delta-sigma modulator.

A new axis: the system level. Every circuit before this one was scored on
a property of the circuit itself - a gain, a delay, an efficiency. Here
the only thing that matters is what comes out of the whole loop after a
decimation filter, and the number, ENOB, belongs to a data converter
rather than to any transistor in it. No single device in the netlist has
an "ENOB"; it exists only for the assembled system.

Which parts are idealised is a deliberate choice, and it is the same
choice bandgap and ldo make. The quantizer is a sign detector sampled by
a track/hold, and the feedback DAC is an ideal E source: neither is being
designed. The loop filter is NOT idealised - it is a real gm-C
integrator built from a differential pair, because its transconductance
and its bias current are precisely the things the design has to get
right, and they are also where the power goes.

The trade-offs the loop imposes:

  * the integrator gain per clock is roughly gm*T/Ci, and it wants to be
    near one. Too little (a large Ci, a weak gm) and the loop barely
    shapes the quantization noise at all; too much and the integrator
    slews into its own rails and the shaping collapses again;
  * gm comes from the differential pair, so buying integrator gain means
    buying bias current, and the power is measured;
  * the DAC reference sets the full scale. A larger Vref keeps the
    modulator out of overload and lifts the SNDR, but the pair only stays
    linear while the differential input stays inside its overdrive, so
    Vref cannot simply be raised without widening the pair;
  * the input amplitude is a design choice too. More signal is more SNDR
    right up until the modulation index approaches one, where a
    first-order loop becomes unstable and the SNDR falls off a cliff.

ENOB and SNDR are two views of one measurement - ENOB is (SNDR-1.76)/6.02
by definition - so meeting the harder of the two targets meets both. They
are both listed because a converter is specified on both.
"""

from .base import MOS_MODELS_PROMPT, Circuit, Metric, load_netlist

PARAM_NAMES = ("W1", "L1", "Ib", "Ci", "Vref", "Ain")

# the bounds are tighter than the other circuits' on purpose: a
# delta-sigma loop far outside its design region does not fail cleanly,
# it hunts, and ngspice then spends seconds on a candidate that was never
# going to be useful. Keeping the space physically sensible is cheaper
# than timing those corners out one by one.
BOUNDS = {
    "W1": (10e-6, 200e-6), "L1": (0.5e-6, 3e-6),
    "Ib": (10e-6, 500e-6),
    "Ci": (5e-12, 200e-12),
    "Vref": (0.08, 0.6),
    "Ain": (0.02, 0.35),
}

REFERENCE = {"W1": 40e-6, "L1": 1e-6, "Ib": 100e-6,
             "Ci": 66e-12, "Vref": 0.25, "Ain": 0.12}

SKELETON = """Vin inp 0 DC 1.2 SIN(1.2 {Ain} 125000)   ; 125 kHz test tone
Vclk clk 0 PULSE(0 3.3 0 1n 1n 30n 100n) ; 10 MHz sampling clock
M1 om inp tail 0 NMOS W={W1} L={L1}      ; gm-C integrator: real diff pair
M2 op  inn tail 0 NMOS W={W1} L={L1}
M5 tail nb 0 0 NMOS W=40u L=1u
M6 nb   nb 0 0 NMOS W=40u L=1u
Ibs vdd nb {Ib}
M3 om om vdd vdd PMOS W=20u L=1u         ; mirror load
M4 op om vdd vdd PMOS W=20u L=1u
Cint op 0 {Ci}                           ; integrating capacitor
Bq qc 0 V = v(op) > 1.65 ? 1 : -1        ; 1-bit quantizer (ideal)
Ssh qc qh clk 0 SWSH                     ; sampled by a track/hold
Csh qh 0 0.1p
Efb inn 0 VALUE={1.2 + {Vref}*v(qh)}     ; 1-bit feedback DAC (ideal)"""

MODELS = MOS_MODELS_PROMPT + """
Supply 3.3 V, common mode 1.2 V, sampling clock 10 MHz, test tone 125 kHz.
The bitstream is decimated by a FIXED three-section RC filter (1k/1n per
section, corner near 159 kHz) that is part of the measurement, not of the
design. Over a 16 us window the filtered output is projected onto the test tone:
what lands on the tone is signal, everything else in the window is noise
plus distortion.
  sndr_db = 10*log10(signal power / noise+distortion power)
  enob    = (sndr_db - 1.76) / 6.02
  power_w = 3.3 V times the average supply current"""


def parse(files):
    """
    mod1.txt -> [signal amplitude, SNDR dB, power].

    ENOB is formed here from the SNDR that the .control block measured:
    it is a definition, not a second measurement, and doing it in Python
    keeps the netlist to the quantities ngspice can actually integrate.
    """
    sig, sndr, pwr = files["mod1.txt"]
    # no tone recovered at the output, or no supply current, means the
    # loop never ran - not a modulator with a poor SNDR
    if sig <= 0 or pwr <= 0:
        return None
    return {
        "enob": (sndr - 1.76) / 6.02,
        "sndr_db": sndr,
        "power_w": pwr,
    }


CIRCUIT = Circuit(
    name="mod1",
    title="first-order delta-sigma modulator",
    summary="system level: ENOB of a whole loop, not of any one device",
    netlist=load_netlist("mod1.sp"),
    param_names=PARAM_NAMES,
    bounds=BOUNDS,
    reference=REFERENCE,
    metrics=(
        Metric("enob", "min", "bits", "Effective bits", (1.0, 12.0)),
        Metric("sndr_db", "min", "dB", "SNDR in band", (8.0, 75.0)),
        Metric("power_w", "max", "W", "Total power", (1e-5, 5e-2)),
    ),
    outputs=(("mod1.txt", 3),),
    # A BACKSTOP ONLY. The record length and the bounds are what keep this
    # circuit affordable; this cap exists to catch a genuinely stuck run.
    # It must stay far above any normal runtime: a timeout that fires on a
    # merely slow candidate makes simulate() depend on machine load, and
    # the same reference then passes alone and fails under parallel
    # generation - which shows up as a reference baseline below 100% and
    # looks like a broken generator.
    timeout=30.0,
    parse=parse,
    skeleton=SKELETON,
    models_block=MODELS,
    hint="The integrator gain per clock is gm*T/Ci with gm = sqrt(2*KP*"
         "(W1/L1)*Ib/2) and T = 100 ns; a first-order loop wants it near "
         "unity. Ideal first-order shaping would give about "
         "30*log10(OSR) - 5.2 dB with OSR = fs/(2*159 kHz), so the gap "
         "between that and the measured SNDR is what slewing, overload and "
         "the finite decimation filter are costing.",
)
