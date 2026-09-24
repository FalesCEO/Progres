* kuijk bandgap voltage reference (ideal-amp model)
.options gmin=1e-12 reltol=1e-4 abstol=1e-13 vntol=1e-7 itl1=500 noacct

.model QN NPN (IS=1e-17 BF=150 VAF=60 RB=10 RE=1)

Vdd vdd 0 3.3
* --- ideal error amplifier: forces v(na) = v(nb) ---
Eop vref 0 na nb 1e5
* --- ctat branch: vbe of q1 ---
R1 vref na {R1}
Q1 na na 0 0 QN area={A1}
* --- ptat branch: delta-vbe developed across r3 ---
R2 vref nb {R2}
R3 nb nc {R3}
Q2 nc nc 0 0 QN area={A2}

.control
set noaskquit
op
let pwr = abs(i(Eop)) * 3.3
echo "$&pwr" > power.txt
dc temp -40 125 5
meas dc vmin MIN v(vref)
meas dc vmax MAX v(vref)
meas dc vnom FIND v(vref) AT=27
let tc = 1e6 * (vmax - vmin) / (vnom * 165)
echo "$&vnom $&tc" > bg.txt
quit
.endc
.end
