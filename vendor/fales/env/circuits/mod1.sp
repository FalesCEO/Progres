* first-order delta-sigma modulator, 10 MHz clock
.options gmin=1e-12 reltol=1e-4 abstol=1e-13 vntol=1e-7 itl1=500 noacct

.model NMOS NMOS (LEVEL=1 VTO=0.7 KP=110u GAMMA=0.4 LAMBDA=0.04
+ TOX=20n PHI=0.7 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)
.model PMOS PMOS (LEVEL=1 VTO=-0.7 KP=50u GAMMA=0.57 LAMBDA=0.05
+ TOX=20n PHI=0.8 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)
.model SWSH SW(RON=200 ROFF=1e12 VT=1.65 VH=0.2)

Vdd vdd 0 3.3
* 125 kHz test tone on a 1.2 V common mode; amplitude is a design choice
Vin inp 0 DC 1.2 SIN(1.2 {Ain} 125000)
Vclk clk 0 PULSE(0 3.3 0 1n 1n 30n 100n)

* --- loop filter: a real gm-C integrator. the diff pair is NOT idealised,
*     because gm and the bias current are exactly what has to be designed ---
M1 om inp tail 0 NMOS W={W1} L={L1}
M2 op  inn tail 0 NMOS W={W1} L={L1}
M5 tail nb 0 0 NMOS W=40u L=1u
M6 nb   nb 0 0 NMOS W=40u L=1u
Ibs vdd nb {Ib}
M3 om om vdd vdd PMOS W=20u L=1u
M4 op om vdd vdd PMOS W=20u L=1u
Cint op 0 {Ci}

* --- 1-bit quantizer: sign detector sampled by a track/hold ---
Bq qc 0 V = v(op) > 1.65 ? 1 : -1
Ssh qc qh clk 0 SWSH
Csh qh 0 0.1p
Rleak qh 0 100meg

* --- ideal 1-bit dac closing the loop back onto the summing input ---
Efb inn 0 VALUE={1.2 + {Vref}*v(qh)}

* --- fixed measurement filter: three rc sections at ~159 kHz. this is the
*     decimation filter of the measurement, not part of the design ---
Rf1 qh f1 1k
Cf1 f1 0 1n
Rf2 f1 f2 1k
Cf2 f2 0 1n
Rf3 f2 f3 1k
Cf3 f3 0 1n

.control
set noaskquit
tran 10n 25.6u

* the signal is recovered by projecting the filtered bitstream onto the
* test tone; everything left over in the band is noise plus distortion.
* the window starts at 9.6 us so the rc filter has settled, and spans
* exactly two periods of the 125 kHz tone
let w = 2*pi*125000*time
let yc = v(f3)*cos(w)
let ys = v(f3)*sin(w)
meas tran ydc AVG v(f3) FROM=9.6u TO=25.6u
meas tran yc1 AVG yc FROM=9.6u TO=25.6u
meas tran ys1 AVG ys FROM=9.6u TO=25.6u
let sig = 2*sqrt(yc1*yc1+ys1*ys1)
let ysq = (v(f3)-ydc)^2
meas tran ytot AVG ysq FROM=9.6u TO=25.6u
let np = ytot - sig*sig/2
let sndr = 10*log10((sig*sig/2)/np)
let pwr = 3.3*mean(abs(i(Vdd)))
echo "$&sig $&sndr $&pwr" > mod1.txt
quit
.endc
.end
