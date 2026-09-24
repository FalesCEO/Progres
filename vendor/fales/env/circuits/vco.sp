* three-stage current-starved ring oscillator
.options gmin=1e-12 reltol=1e-4 abstol=1e-13 vntol=1e-7 itl1=500 noacct

.model NMOS NMOS (LEVEL=1 VTO=0.7 KP=110u GAMMA=0.4 LAMBDA=0.04
+ TOX=20n PHI=0.7 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)
.model PMOS PMOS (LEVEL=1 VTO=-0.7 KP=50u GAMMA=0.57 LAMBDA=0.05
+ TOX=20n PHI=0.8 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)

Vdd vdd 0 3.3
* the control voltage is split in two so the sweep step can be applied by
* altering a source instead of evaluating arithmetic in the netlist
Vctrl ctrl cx {Vc}
Vdelta cx 0 0

* a ring has no stable dc solution to start from - the initial condition
* kicks it and every run is done with uic
.ic v(n1)=0 v(n2)=3.3 v(n3)=0

* --- stage 1: inverter whose ground return is starved by Ms1 ---
Mp1 n1 n3 vdd vdd PMOS W={Wp} L={L}
Mn1 n1 n3 s1 0 NMOS W={Wn} L={L}
Ms1 s1 ctrl 0 0 NMOS W={Ws} L={L}
C1 n1 0 {Cl}
* --- stage 2 ---
Mp2 n2 n1 vdd vdd PMOS W={Wp} L={L}
Mn2 n2 n1 s2 0 NMOS W={Wn} L={L}
Ms2 s2 ctrl 0 0 NMOS W={Ws} L={L}
C2 n2 0 {Cl}
* --- stage 3 ---
Mp3 n3 n2 vdd vdd PMOS W={Wp} L={L}
Mn3 n3 n2 s3 0 NMOS W={Wn} L={L}
Ms3 s3 ctrl 0 0 NMOS W={Ws} L={L}
C3 n3 0 {Cl}

.control
set noaskquit

* --- run 1: nominal control voltage and nominal supply ---
tran 0.5n 500n uic
meas tran ta WHEN v(n1)=1.65 RISE=3
meas tran tb WHEN v(n1)=1.65 RISE=8
let f0 = 5/(tb-ta)
let pwr = 3.3*mean(abs(i(Vdd)))
* each run opens a new plot, so every result is written out before the
* next tran starts - scalars do not survive a plot change
echo "$&f0 $&pwr" > f0.txt

* --- run 2: control voltage stepped by +200 mV -> tuning gain ---
alter Vdelta = 0.2
tran 0.5n 500n uic
meas tran tc WHEN v(n1)=1.65 RISE=3
meas tran td WHEN v(n1)=1.65 RISE=8
let f1 = 5/(td-tc)
echo "$&f1" > f1.txt

* --- run 3: control restored, supply stepped by +200 mV -> pushing ---
alter Vdelta = 0
alter Vdd = 3.5
tran 0.5n 500n uic
meas tran te WHEN v(n1)=1.65 RISE=3
meas tran tf WHEN v(n1)=1.65 RISE=8
let f2 = 5/(tf-te)
echo "$&f2" > f2.txt
quit
.endc
.end
