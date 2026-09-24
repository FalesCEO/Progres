* low-dropout regulator: pmos pass device + gm error amp
.options gmin=1e-12 reltol=1e-4 abstol=1e-13 vntol=1e-7 itl1=500 noacct

.model PMOS PMOS (LEVEL=1 VTO=-0.7 KP=50u GAMMA=0.57 LAMBDA=0.05
+ TOX=20n PHI=0.8 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)

Vdd vdd 0 DC 3.3 AC 0
Vref ref 0 1.2

* --- error amplifier: gm stage, output resistance to vdd, gain = gm*ro ---
Gea ea 0 ref fbin {Gm}
Roa vdd ea {Ro}
Cc ea 0 {Cc}

* --- pmos pass device ---
Mp out ea vdd vdd PMOS W={Wp} L={Lp}

* --- feedback divider: vout = 1.2 * (1 + r1/r2) ---
R1 out fb {R1}
R2 fb 0 {R2}

* --- output network and fixed 10 ma load ---
Cout out oe {Cout}
Resr oe 0 {Resr}
Iload out 0 10m

* --- loop break: lb shorts at dc and opens at ac, cinj injects at ac ---
Lb fb fbin 1G
Vinj inj 0 DC 0 AC 1
Cinj inj fbin 1G

.control
set noaskquit
op
let vo = v(out)
let iq = abs(i(Vdd)) - 10e-3
echo "$&vo $&iq" > dc.txt

* --- loop gain: t(s) = -v(fb) while v(fbin) is driven to 1 ---
ac dec 40 1 100meg
let tdb = db(v(fb))
let tph = 180/pi * ph(v(fb))
meas ac tdc FIND tdb AT=1
meas ac phdc FIND tph AT=1
meas ac ugf WHEN tdb=0 FALL=1
meas ac phugf FIND tph WHEN tdb=0 FALL=1
echo "$&tdc $&ugf $&phugf $&phdc" > ac.txt

* --- psrr: close the loop again, move the ac drive to the supply ---
alter Lb = 1p
alter Cinj = 1f
alter Vinj acmag = 0
alter Vdd acmag = 1
ac dec 20 10 10meg
let odb = db(v(out))
meas ac psrr FIND odb AT=1k
echo "$&psrr" > psrr.txt
quit
.endc
.end
