* source-follower voltage buffer driving a resistive load
.options gmin=1e-12 reltol=1e-7 abstol=1e-14 vntol=1e-8 itl1=500 noacct

.model NMOS NMOS (LEVEL=1 VTO=0.7 KP=110u GAMMA=0.4 LAMBDA=0.04
+ TOX=20n PHI=0.7 CGSO=0.4n CGDO=0.4n CJ=0.4m CJSW=0.8n MJ=0.5)

Vdd vdd 0 3.3
* fixed stimulus: 0.7 V amplitude at 10 kHz, exactly 2 periods are simulated
Vin in 0 DC {Vcm} SIN({Vcm} 0.7 10k)

* --- follower device ---
M1 vdd in out 0 NMOS W={W1} L={L1}
* --- tail current source and its bias mirror ---
M2 out nbias 0 0 NMOS W={W2} L={L2}
M3 nbias nbias 0 0 NMOS W={W2} L={L2}
Ibs vdd nbias {Ib}
* --- load ---
RL out 0 {RL}
CL out 0 5p

.control
set noaskquit
op
let iq = abs(i(Vdd))
echo "$&iq" > dc.txt

tran 20n 200u
linearize v(out)

* harmonics by direct projection onto sin/cos. the record covers exactly
* two periods and linearize makes the sampling uniform, so mean() is an
* exact quadrature and no windowing or zero padding is involved
let w = 2*pi*10e3*time
let h1 = sqrt((2*mean(v(out)*cos(w)))^2   + (2*mean(v(out)*sin(w)))^2)
let h2 = sqrt((2*mean(v(out)*cos(2*w)))^2 + (2*mean(v(out)*sin(2*w)))^2)
let h3 = sqrt((2*mean(v(out)*cos(3*w)))^2 + (2*mean(v(out)*sin(3*w)))^2)
let h4 = sqrt((2*mean(v(out)*cos(4*w)))^2 + (2*mean(v(out)*sin(4*w)))^2)
let h5 = sqrt((2*mean(v(out)*cos(5*w)))^2 + (2*mean(v(out)*sin(5*w)))^2)
let thd = 100*sqrt(h2^2+h3^2+h4^2+h5^2)/h1
let sw = maximum(v(out)) - minimum(v(out))
echo "$&thd $&sw $&h1" > thd.txt
quit
.endc
.end
