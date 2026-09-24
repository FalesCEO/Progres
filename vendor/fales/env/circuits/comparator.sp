* comparator with hysteresis (cross-coupled positive feedback load)
.options gmin=1e-12 reltol=1e-4 abstol=1e-13 vntol=1e-7 itl1=500 noacct

.model NMOS NMOS (LEVEL=1 VTO=0.7 KP=110u GAMMA=0.4 LAMBDA=0.04
+ TOX=20n PHI=0.7 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)
.model PMOS PMOS (LEVEL=1 VTO=-0.7 KP=50u GAMMA=0.57 LAMBDA=0.05
+ TOX=20n PHI=0.8 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)

Vdd vdd 0 3.3
Vinn inn 0 1.2
* slow triangle 0.6 -> 1.8 -> 0.6 extracts both trip points,
* then two 1 ns edges give the propagation delay
Vinp inp 0 PWL(0 0.6 10u 1.8 20u 0.6 20.001u 0.6 20.002u 1.8
+ 25u 1.8 25.001u 0.6 30u 0.6)

* --- input differential pair ---
M1 n1 inp tail 0 NMOS W={W1} L={L1}
M2 n2 inn tail 0 NMOS W={W1} L={L1}
* --- diode-connected load ---
M3 n1 n1 vdd vdd PMOS W={W3} L={L3}
M4 n2 n2 vdd vdd PMOS W={W3} L={L3}
* --- cross-coupled pair: w6/w3 above 1 creates the hysteresis ---
M6 n1 n2 vdd vdd PMOS W={W6} L={L6}
M7 n2 n1 vdd vdd PMOS W={W6} L={L6}
* --- tail current source + bias mirror ---
M5 tail nbias 0 0 NMOS W={W5} L={L5}
M9 nbias nbias 0 0 NMOS W={W5} L={L5}
Ibs vdd nbias {Ib}
* --- gain stage (non-inverting overall) ---
M8 o1 n2 vdd vdd PMOS W={W8} L={L8}
M10 o1 nbias 0 0 NMOS W={W9} L={L9}
* --- output inverter for a rail-to-rail edge ---
M11 out o1 vdd vdd PMOS W=20u L=1u
M12 out o1 0 0 NMOS W=8u L=1u
CLc out 0 0.2p

.control
set noaskquit
op
let pwr = abs(i(Vdd)) * 3.3
echo "$&pwr" > power.txt
tran 5n 30u
* trip points from the slow triangle (first rise / first fall)
meas tran vth FIND v(inp) WHEN v(out)=1.65 RISE=1
meas tran vtl FIND v(inp) WHEN v(out)=1.65 FALL=1
* propagation delay from the fast edge (second rise)
meas tran tpr TRIG v(inp) VAL=1.2 RISE=2 TARG v(out) VAL=1.65 RISE=2
echo "$&vth $&vtl $&tpr" > cmp.txt
quit
.endc
.end
