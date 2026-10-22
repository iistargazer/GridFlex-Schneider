"""Static HTML dashboard (Chart.js) + PNG figures for the deck."""
import json, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = lambda a: [round(float(x), 1) for x in a]


def _days(P, runs):
    g = runs["gridflex"]; u = runs["unmanaged"]; out = []
    for d in range(len(g) // 96):
        s = slice(d * 96, (d + 1) * 96); gs, us = g.iloc[s], u.iloc[s]
        out_steps = np.where(gs.cap.values == 0)[0]
        tag = []
        if gs.cap.values.min() == 0: tag.append(f"outage {out_steps[0]//4:02d}:{out_steps[0]%4*15:02d}")
        if (gs.cap.values < P.cap_normal).any() and gs.cap.values.max() > 0 and (gs.cap.values == P.cap_stress).any(): tag.append("DISCOM stress")
        out.append(dict(label=f"{gs.index[0].date()} {'· ' + ', '.join(tag) if tag else '· normal'}",
                        interrupted_unmanaged=round(float((us.shed_c > 0.05 * us.Dc).sum() * .25), 2),
                        interrupted_gridflex=round(float((gs.shed_c > 0.05 * gs.Dc).sum() * .25), 2),
                        load=R(gs.Dc + gs.F), pv=R(gs.pv), cap=R(gs.cap),
                        g_u=R(us.g), g_f=R(gs.g), soc_u=R(us.soc), soc_f=R(gs.soc),
                        shed_u=R(us.shed_c), shed_f=R(gs.shed_c)))
    return out


def make_dashboard(P, runs, M, econ, acc, path):
    data = dict(days=_days(P, runs), M=M, econ=econ, acc=acc, bat=P.bat_kwh)
    html = HTML.replace("__DATA__", json.dumps(data))
    open(path, "w").write(html)


def make_plots(P, runs, M, outdir):
    days = _days(P, runs)
    k = int(np.argmax([d["interrupted_unmanaged"] - d["interrupted_gridflex"] for d in days]))
    d, x = days[k], np.arange(96) / 4
    fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax[0].plot(x, d["load"], label="Load", c="k"); ax[0].plot(x, d["pv"], label="Solar", c="orange")
    ax[0].plot(x, d["g_f"], label="Grid import (GridFlex)", c="g"); ax[0].step(x, d["cap"], label="Feeder limit", c="r", ls="--")
    ax[0].set_ylabel("kW"); ax[0].legend(ncol=4, fontsize=8); ax[0].set_title(d["label"])
    ax[1].plot(x, d["soc_u"], label="Battery kWh - unmanaged", c="gray"); ax[1].plot(x, d["soc_f"], label="Battery kWh - GridFlex", c="g")
    ax[1].fill_between(x, d["shed_u"], color="gray", alpha=.3, label="Critical load unserved kW - unmanaged")
    ax[1].fill_between(x, d["shed_f"], color="g", alpha=.4, label="Critical load unserved kW - GridFlex")
    ax[1].set_xlabel("hour"); ax[1].legend(fontsize=8); plt.tight_layout(); plt.savefig(f"{outdir}/day_plot.png", dpi=140); plt.close()
    fig, ax = plt.subplots(figsize=(6, 3.5)); ks = ["status_quo", "unmanaged", "gridflex"]
    ax.bar(["Grid only", "PV+battery\n(unmanaged)", "GridFlex"], [M[i]["outage_hours_per_day"] for i in ks], color=["#b33", "#999", "#2a7"])
    ax.set_ylabel("Hours/day critical supply interrupted"); plt.tight_layout(); plt.savefig(f"{outdir}/outage_hours.png", dpi=140); plt.close()


HTML = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GridFlex dashboard</title><script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>:root{--bg:#fff;--fg:#1a1a1a;--card:#f2f6f2;--ac:#2a7a3b}@media(prefers-color-scheme:dark){:root{--bg:#15191a;--fg:#e8ece8;--card:#222a26}}
body{margin:0;padding:16px;font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:1100px;margin:auto}
.k{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}.c{background:var(--card);border-radius:10px;padding:12px}
.c b{font-size:1.5em;color:var(--ac)}table{width:100%;border-collapse:collapse}td,th{padding:5px;border-bottom:1px solid #8884;text-align:right}td:first-child,th:first-child{text-align:left}
select{padding:6px;font-size:1em;max-width:100%}.w{position:relative;height:280px}small{opacity:.7}</style></head><body>
<h1>GridFlex - neighbourhood feeder dashboard <small>(simulated data)</small></h1><div class="k" id="k"></div>
<h3>Scenario comparison (held-out test days)</h3><div style="overflow-x:auto"><table id="t"></table></div>
<h3>Day view: <select id="s"></select></h3><div class="w"><canvas id="a"></canvas></div><div class="w"><canvas id="b"></canvas></div>
<h3>Unit economics per household (assumptions)</h3><table id="e"></table>
<p><small>Forecast day-ahead error on held-out days: load MAPE <span id="f1"></span>%, PV nMAE <span id="f2"></span>%. Data is synthetic; do not quote as field results.</small></p>
<script>const D=__DATA__,M=D.M,$=i=>document.getElementById(i),f=(x,n=1)=>(+x).toFixed(n);
const g=M.gridflex,u=M.unmanaged,q=M.status_quo;
$('k').innerHTML=[[f(g.outage_hours_per_day,2),'h/day critical supply interrupted (GridFlex) vs '+f(u.outage_hours_per_day,2)+' unmanaged, '+f(q.outage_hours_per_day,2)+' grid-only'],
[f(g.evening_availability_pct)+'%','evening (18-23h) availability vs '+f(u.evening_availability_pct)+'% unmanaged'],
[f(g.evening_peak_import_kw)+' kW','avg evening peak feeder import vs '+f(u.evening_peak_import_kw)+' kW'],
[f(g.bill_inr_per_hh_month,0),'Rs/household/month grid bill vs '+f(u.bill_inr_per_hh_month,0)]].map(x=>`<div class=c><b>${x[0]}</b><br>${x[1]}</div>`).join('');
const rows=[['critical_served_pct','Critical energy served %'],['outage_hours_per_day','Interrupted hours/day'],['evening_availability_pct','Evening availability %'],['unserved_critical_kwh_per_day','Unserved critical kWh/day'],['flex_unserved_kwh_per_day','Flexible kWh lost/day'],['curtailment_pct','Solar curtailed %'],['evening_peak_import_kw','Evening peak import kW'],['grid_energy_kwh_per_day','Grid energy kWh/day'],['bill_inr_per_hh_month','Bill Rs/hh/month']];
$('t').innerHTML='<tr><th></th><th>Grid only</th><th>Unmanaged PV+battery</th><th>GridFlex</th></tr>'+rows.map(r=>`<tr><td>${r[1]}</td><td>${f(q[r[0]],2)}</td><td>${f(u[r[0]],2)}</td><td>${f(g[r[0]],2)}</td></tr>`).join('');
const E=D.econ;$('e').innerHTML=Object.entries(E).map(([k,v])=>`<tr><td>${k.replace(/_/g,' ')}</td><td>${f(v,0)}</td></tr>`).join('');
$('f1').textContent=f(D.acc.load_mape_pct);$('f2').textContent=f(D.acc.pv_nmae_pct);
$('s').innerHTML=D.days.map((d,i)=>`<option value=${i}>${d.label}</option>`).join('');
const X=[...Array(96).keys()].map(i=>String(i>>2).padStart(2,'0')+':'+String(i%4*15).padStart(2,'0'));
const L=(l,d,c,o={})=>({label:l,data:d,borderColor:c,backgroundColor:c,pointRadius:0,borderWidth:2,...o});
const opt=(y)=>({responsive:true,maintainAspectRatio:false,animation:false,scales:{y:{title:{display:true,text:y}},x:{ticks:{maxTicksLimit:12}}}});
const A=new Chart($('a'),{type:'line',data:{labels:X,datasets:[]},options:opt('kW')}),B=new Chart($('b'),{type:'line',data:{labels:X,datasets:[]},options:opt('kWh / kW')});
function draw(){const d=D.days[$('s').value];
A.data.datasets=[L('Load',d.load,'#222'),L('Solar',d.pv,'#e90'),L('Grid import (GridFlex)',d.g_f,'#2a7a3b'),L('Grid import (unmanaged)',d.g_u,'#999',{borderDash:[4,3]}),L('Feeder limit',d.cap,'#c33',{borderDash:[6,4],stepped:true})];
B.data.datasets=[L('Battery kWh unmanaged',d.soc_u,'#999'),L('Battery kWh GridFlex',d.soc_f,'#2a7a3b'),L('Critical unserved kW unmanaged',d.shed_u,'#555',{fill:true}),L('Critical unserved kW GridFlex',d.shed_f,'#1c4',{fill:true})];A.update();B.update();}
$('s').onchange=draw;draw();</script></body></html>"""
