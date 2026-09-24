* five-transistor single-stage differential amplifier (5t ota)
.options gmin=1e-12 reltol=1e-4 abstol=1e-13 vntol=1e-7 itl1=500 noacct

.model NMOS NMOS (LEVEL=1 VTO=0.7 KP=110u GAMMA=0.4 LAMBDA=0.04
+ TOX=20n PHI=0.7 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)
.model PMOS PMOS (LEVEL=1 VTO=-0.7 KP=50u GAMMA=0.57 LAMBDA=0.05
+ TOX=20n PHI=0.8 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)

Vdd vdd 0 3.3
Vcm cm 0 1.2
Vinp inp cm AC 0.5
Vinn inn cm AC -0.5

* --- input differential pair ---
M1 n1 inp tail 0 NMOS W={W1} L={L1}
M2 out inn tail 0 NMOS W={W1} L={L1}
* --- pmos current mirror load (out is the only high impedance node) ---
M3 n1 n1 vdd vdd PMOS W={W3} L={L3}
M4 out n1 vdd vdd PMOS W={W3} L={L3}
* --- tail current source + bias mirror ---
M5 tail nbias 0 0 NMOS W={W5} L={L5}
M8 nbias nbias 0 0 NMOS W={W5} L={L5}
Ibs vdd nbias {Ib}
CL out 0 2p

.control
set noaskquit
op
let pwr = abs(i(Vdd)) * 3.3
echo "$&pwr" > power.txt
ac dec 60 1 10G
let gdb = db(v(out))
let phs = 180/pi * ph(v(out))
meas ac dcgain FIND gdb AT=10
meas ac phdc FIND phs AT=10
meas ac ugf WHEN gdb=0 FALL=1
meas ac phugf FIND phs WHEN gdb=0 FALL=1
echo "$&dcgain $&ugf $&phugf $&phdc" > ac.txt
quit
.endc
.end
