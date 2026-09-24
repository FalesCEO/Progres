* asynchronous buck converter, fixed 1 MHz switching
.options gmin=1e-12 reltol=1e-4 abstol=1e-12 vntol=1e-6 itl1=500 noacct

* the high-side switch resistance is the design knob for conduction loss
.model SWM SW(RON={Ron} ROFF=1meg VT=2.5 VH=0.1)
* the load-step switch is ideal on purpose: it is stimulus, not design
.model SWL SW(RON=0.01 ROFF=1meg VT=2.5 VH=0.1)
.model DSCH D(IS=1e-6 N=1.0 RS=0.01 CJO=100p)

Vin vin 0 5
* duty is set through the on-time directly, so the netlist needs no
* arithmetic: period is fixed at 1 us, so D = Ton / 1 us
Vpwm pwm 0 PULSE(0 5 0 2n 2n {Ton} 1u)

* --- power stage ---
S1 vin sw pwm 0 SWM
D1 0 sw DSCH
L1 sw out {L}
Cout out oe {Cout}
Resr oe 0 {Resr}
Rload out 0 5

* --- load step: a second 5 ohm load switches in at 100 us ---
Vstep stp 0 PULSE(0 5 100u 10n 10n 100u 300u)
S2 out ld stp 0 SWL
Rld2 ld 0 5

.control
set noaskquit
tran 20n 140u
let pin = 5*abs(i(Vin))
let pout = v(out)*v(out)/5

* steady state is read from a 20 us window that ends just before the
* load step, so the start-up ring is long gone
meas tran vss AVG v(out) FROM=80u TO=100u
meas tran vpp PP v(out) FROM=80u TO=100u
meas tran pi AVG pin FROM=80u TO=100u
meas tran po AVG pout FROM=80u TO=100u
* the droop is the transient undershoot after the load doubles
meas tran vmn MIN v(out) FROM=100u TO=130u
echo "$&vss $&vpp $&pi $&po $&vmn" > buck.txt
quit
.endc
.end
