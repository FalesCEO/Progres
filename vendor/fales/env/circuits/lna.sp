* low-noise amplifier: common source with source degeneration
.options gmin=1e-12 reltol=1e-4 abstol=1e-13 vntol=1e-7 itl1=500 noacct

.model NMOS NMOS (LEVEL=1 VTO=0.7 KP=110u GAMMA=0.4 LAMBDA=0.04
+ TOX=20n PHI=0.7 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)

Vdd vdd 0 3.3
* gate bias doubles as the ac source and as the noise input reference
Vg gate 0 DC {Vg} AC 1

* --- amplifying device, self-biased through the degeneration resistor ---
M1 out gate src 0 NMOS W={W1} L={L1}
Rs src 0 {Rs}
* --- resistive load: sets gain together with gm, and the pole with CL ---
RD vdd out {RD}
CL out 0 1p

.control
set noaskquit
op
let pwr = abs(i(Vdd)) * 3.3
echo "$&pwr" > power.txt

* --- gain and -3 dB bandwidth ---
ac dec 40 1e3 1e10
let gdb = db(v(out))
meas ac g0 FIND gdb AT=1e4
let g3 = g0 - 3
meas ac bw WHEN gdb=g3 FALL=1
echo "$&g0 $&bw" > ac.txt

* --- input-referred noise, integrated over a FIXED 1 kHz .. 1 MHz band.
*     the band is fixed on purpose: integrating past the -3 dB corner
*     would let the referred noise blow up where the gain rolls off, and
*     the noise number would then just re-measure the bandwidth ---
noise v(out) Vg dec 40 1e3 1e6
setplot noise2
let vn = inoise_total
echo "$&vn" > noise.txt
quit
.endc
.end
