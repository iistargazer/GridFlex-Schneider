"""Static, dependency-free dashboard (vendored Chart.js) + PNG figures.

Everything is precomputed in Python so the page works offline in a judging room:
no server, no CDN, no API keys.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .config import assumptions_table
from .data import FLEX
from .network import voltages

R = lambda a: [round(float(x), 2) for x in a]
ASSET = os.path.join(os.path.dirname(__file__), "assets", "chart.umd.min.js")


def _day_pack(P, df, runs, modes):
    full = runs["mpc_full"]
    days = []
    n_days = len(full) // 96
    for d in range(n_days):
        sl = slice(d * 96, (d + 1) * 96)
        g = full.iloc[sl]
        cap = g.cap.values
        outage = bool(g.is_outage.any())
        stress = bool(g.is_stress.any())
        tag = "outage" if outage else ("DISCOM stress" if stress else "normal")
        v = voltages(P, g.g.values)
        item = dict(label=f"{g.index[0].strftime('%d %b')} · {tag}",
                    load=R(g.Dc + g.served_f), pv=R(g.pv), cap=R(cap),
                    g={}, soc={}, shed={}, flex={}, exp=R(g.exp), curt=R(g.curt),
                    v=[R(v[:, b]) for b in range(v.shape[1])])
        for m in modes:
            rr = runs[m].iloc[sl]
            item["g"][m] = R(rr.g)
            item["soc"][m] = R(rr.soc)
            item["shed"][m] = R(rr.shed_c)
        for cls in FLEX:
            item["flex"][cls] = R(g[f"f_{cls}"])
        days.append(item)
    return days


def _reasons(P, runs, df):
    from .explain import day_summary, hourly
    full, base = runs["mpc_full"], runs["pv_batt_naive"]
    diff = [(full.iloc[d * 96:(d + 1) * 96].shed_c.sum()
             - base.iloc[d * 96:(d + 1) * 96].shed_c.sum()) for d in range(len(df) // 96)]
    best = int(np.argmax(diff))
    sl = slice(best * 96, (best + 1) * 96)
    return dict(day=full.index[best * 96].strftime("%d %b %Y"),
                summary=day_summary(P, full, sl),
                hourly=hourly(P, full, sl))


def build_payload(P, df, runs, M, acc, econ, equity, sizing, whatif, discom,
                  ci=None, provenance=None, headline=None):
    modes = ["grid_only", "pv_batt_naive", "rule_reserve_tou", "mpc_no_dr",
             "mpc_persistence", "mpc_full", "oracle"]
    modes = [m for m in modes if m in runs]
    best = runs["mpc_full"].index[0]
    return dict(
        meta=dict(site=P.site_name, start=str(df.index[0].date()), end=str(df.index[-1].date()),
                  days=P.n_days, test_days=P.n_test_days,
                  generated=pd_now(), n_hh=P.n_hh, pv_kwp=P.pv_kwp,
                  bat_kwh=P.bat_kwh, bat_kw=P.bat_kw,
                  outage_h_target=P.outage_h_per_day,
                  outage_h_realised=round(float(df.is_outage.mean() * 24), 2),
                  forecast=acc, provenance=provenance,
                  tariff_mode=P.tariff_mode, tariff=P.tariff_flat,
                  full_day=str(best.date())),
        scenarios=M, headline=headline or {}, ci=ci or {},
        days=_day_pack(P, df, runs, modes),
        reasons=_reasons(P, runs, df),
        equity=equity, econ=econ, sizing=sizing, whatif=whatif, discom=discom,
        assumptions=assumptions_table(P),
        modes=modes,
    )


def pd_now():
    import datetime
    return datetime.datetime.now().strftime("%d %b %Y %H:%M")


def make_dashboard(payload, path, site_path=None):
    """Write the self-contained dashboard, plus its publishable copy.

    One writer, one HTML string: the local page and the file a judge uploads are
    written in the same call, so they cannot drift apart. Chart.js is inlined, so
    no sidecar asset is produced and the page works from a file path or a server.
    """
    chart = open(ASSET, encoding="utf-8").read()
    html = HTML.replace('<script src="chart.umd.min.js"></script>',
                        f"<script>{chart}</script>")
    html = html.replace("__DATA__", json.dumps(payload, default=float))
    for target in ([path] if not site_path else [path, site_path]):
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        open(target, "w", encoding="utf-8").write(html)


# ---------------------------------------------------------------------------
# PNG figures for the deck
# ---------------------------------------------------------------------------
def make_plots(P, df, runs, M, sizing, outdir):
    os.makedirs(outdir, exist_ok=True)
    modes = [m for m in ["grid_only", "pv_batt_naive", "rule_reserve_tou",
                         "mpc_no_dr", "mpc_persistence", "mpc_full", "oracle"] if m in M]
    labels = [m.replace("_", "\n") for m in modes]
    colors = ["#b3402f", "#8a8f98", "#c98b2e", "#5b7fbf", "#7a5fa8", "#1f7a4d", "#0f5132"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].bar(labels, [M[m]["outage_hours_per_day"] for m in modes], color=colors)
    ax[0].set_ylabel("interrupted critical hours/day")
    ax[0].set_title("Reliability by scenario")
    ax[1].bar(labels, [M[m]["bill_inr_per_hh_month"] for m in modes], color=colors)
    ax[1].set_ylabel("Rs / household / month")
    ax[1].set_title("Grid bill by scenario")
    for a in ax:
        a.tick_params(axis="x", labelsize=7)
    plt.tight_layout()
    plt.savefig(f"{outdir}/scenarios.png", dpi=150)
    plt.close()

    # worst day
    full, base = runs["mpc_full"], runs["pv_batt_naive"]
    diff = [(full.iloc[d * 96:(d + 1) * 96].shed_c.sum()
             - base.iloc[d * 96:(d + 1) * 96].shed_c.sum()) for d in range(len(df) // 96)]
    k = int(np.argmax(diff))
    sl = slice(k * 96, (k + 1) * 96)
    g, u = full.iloc[sl], base.iloc[sl]
    x = np.arange(96) / 4
    fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax[0].plot(x, g.Dc + g.served_f, "k", label="Load")
    ax[0].plot(x, g.pv, "#e8a33d", label="Solar")
    ax[0].plot(x, g.g, "#1f7a4d", label="Grid import - GridFlex")
    ax[0].plot(x, u.g, "#8a8f98", ls="--", label="Grid import - unmanaged")
    ax[0].step(x, g.cap, "#b3402f", ls=":", label="Feeder limit")
    ax[0].legend(ncol=3, fontsize=8)
    ax[0].set_ylabel("kW")
    ax[0].set_title(g.index[0].strftime("%d %b %Y"))
    ax[1].plot(x, g.soc, "#1f7a4d", label="SOC - GridFlex")
    ax[1].plot(x, u.soc, "#8a8f98", label="SOC - unmanaged")
    ax[1].fill_between(x, g.shed_c, color="#1f7a4d", alpha=.35, label="unserved critical")
    ax[1].fill_between(x, u.shed_c, color="#b3402f", alpha=.25, label="unserved - unmanaged")
    ax[1].set_ylabel("kWh / kW")
    ax[1].set_xlabel("hour")
    ax[1].legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(f"{outdir}/day_plot.png", dpi=150)
    plt.close()

    if sizing and sizing.get("points"):
        pts = sizing["points"]
        fig, ax = plt.subplots(figsize=(6, 4))
        for scheme, colour in (("lifeline", "#1f7a4d"), ("flat", "#c98b2e")):
            s = [p for p in pts if p.get("fee_scheme") == scheme]
            if not s:
                continue
            ax.scatter([p["outage_hours_per_day"] for p in s],
                       [p["net_cost_low_income_per_hh_month_inr"] for p in s],
                       c=colour, label=f"{scheme} tariff")
            for p in s:
                ax.annotate(f"{p['bat_kwh']:.0f}kWh", (p["outage_hours_per_day"],
                                                       p["net_cost_low_income_per_hh_month_inr"]),
                            fontsize=7, xytext=(4, 3), textcoords="offset points")
        ax.set_xlabel("interrupted critical hours/day")
        ax.set_ylabel("net cost, low-income Rs/hh/month")
        ax.set_title("Battery sizing frontier by tariff")
        ax.legend(fontsize=7)
        plt.tight_layout()
        plt.savefig(f"{outdir}/sizing.png", dpi=150)
        plt.close()

    fig, ax = plt.subplots(figsize=(6, 4))
    v = voltages(P, full.g.values)
    for b in range(v.shape[1]):
        ax.plot(np.arange(len(v)) / 96, v[:, b], label=f"branch {b+1}")
    ax.axhline(P.v_min_pu, color="#b3402f", ls="--", label="limit")
    ax.set_ylim(0.92, 1.01)
    ax.set_xlabel("day"); ax.set_ylabel("voltage (pu)")
    ax.set_title("End-of-feeder voltage, GridFlex")
    ax.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(f"{outdir}/voltage.png", dpi=150)
    plt.close()


HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GridFlex · neighbourhood reliability dashboard</title>
<script src="chart.umd.min.js"></script>
<style>
:root{--bg:#fbfbf9;--fg:#17201b;--muted:#5d6b62;--card:#f0f4ef;--line:#d8e0d9;--ac:#1f7a4d;--warn:#b3402f;--amber:#c98b2e}
@media (prefers-color-scheme:dark){:root{--bg:#121715;--fg:#e7eee9;--muted:#9fb0a6;--card:#1c2420;--line:#2c3733;--ac:#49b57e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:22px 22px 8px;max-width:1180px;margin:auto}
h1{font-size:1.45rem;margin:0 0 4px}h2{font-size:1.05rem;margin:22px 0 8px}h3{font-size:.95rem;margin:14px 0 6px}
.sub{color:var(--muted);font-size:.86rem}
nav{display:flex;gap:6px;flex-wrap:wrap;padding:6px 22px 0;max-width:1180px;margin:auto}
nav button{border:1px solid var(--line);background:transparent;color:var(--fg);padding:7px 12px;border-radius:999px;cursor:pointer;font-size:.85rem}
nav button.on{background:var(--ac);border-color:var(--ac);color:#fff}
main{max-width:1180px;margin:auto;padding:6px 22px 60px}.tab{display:none}.tab.on{display:block}
.k{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0}
.c{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.c b{display:block;font-size:1.5rem;color:var(--ac);font-weight:650}.c span{color:var(--muted);font-size:.8rem}
table{width:100%;border-collapse:collapse;font-size:.86rem;margin:8px 0}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right}
th:first-child,td:first-child{text-align:left}thead th{color:var(--muted);font-weight:600}
.w{position:relative;height:270px;margin:8px 0 18px}.w.tall{height:330px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:800px){.row{grid-template-columns:1fr}}
.pill{display:inline-block;font-size:.72rem;border:1px solid var(--line);border-radius:999px;padding:2px 8px;color:var(--muted);margin-right:4px}
.real{border-color:var(--ac);color:var(--ac)}.assume{border-color:var(--amber);color:var(--amber)}
select,input[type=range]{width:100%;padding:6px;background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:8px}
.small{font-size:.8rem;color:var(--muted)}
ul{padding-left:18px}li{margin:3px 0}
code{background:var(--card);padding:1px 5px;border-radius:4px;font-size:.85em}
.note{border-left:3px solid var(--amber);padding:6px 10px;background:var(--card);border-radius:0 8px 8px 0;font-size:.84rem}
</style></head><body>
<header><h1>GridFlex · neighbourhood reliability dashboard</h1>
<div class="sub" id="sub"></div>
<div style="margin-top:8px"><span class="pill real">real weather</span><span class="pill real">real day-ahead forecast</span><span class="pill">calibrated load</span><span class="pill assume">simulated outages</span><span class="pill assume">cost assumptions</span></div></header>
<nav id="nav"></nav>
<main>
<section class="tab on" id="t-overview">
  <h2>Did the neighbourhood stay supplied?</h2>
  <div class="k" id="kpis"></div>
  <p class="note">All scenarios run on identical weather, load and outage draws. Headline numbers are the multi-seed mean when <code>--seeds</code> is used; otherwise a single seed on the held-out days.</p>
  <h2>Scenario comparison (held-out test days)</h2>
  <div style="overflow-x:auto"><table id="scen"></table></div>
  <h2>Day view <select id="daysel" style="max-width:280px;display:inline-block"></select></h2>
  <div class="w tall"><canvas id="day1"></canvas></div>
  <div class="w"><canvas id="day2"></canvas></div>
  <div class="row"><div><h3>What happened that day</h3><div id="summary" class="small"></div></div>
  <div><h3>Why the controller acted</h3><ul id="reasons" class="small"></ul></div></div>
</section>

<section class="tab" id="t-scenarios">
  <h2>Ablation: which component earns the gain?</h2>
  <p class="sub">Every scenario is the same plant, weather, load and outages. "MPC no DR" switches off flexible-load shifting; "MPC persistence" swaps the ML forecaster for yesterday.</p>
  <div class="w tall"><canvas id="ablation"></canvas></div>
  <div style="overflow-x:auto"><table id="abtable"></table></div>
  <div class="w"><canvas id="billbars"></canvas></div>
  <h3>Multi-seed confidence intervals</h3>
  <p class="sub" id="cinote"></p>
  <div style="overflow-x:auto"><table id="citable"></table></div>
</section>

<section class="tab" id="t-discom">
  <h2>DISCOM console</h2>
  <div class="k" id="discomkpis"></div>
  <div class="row">
    <div><h3>Next-day feeder risk</h3><div class="w"><canvas id="risk"></canvas></div></div>
    <div><h3>End-of-feeder voltage (selected day)</h3><div class="w"><canvas id="volt"></canvas></div></div>
  </div>
  <h3>Recommended demand-response actions</h3><ul id="actions" class="small"></ul>
  <h3>Technical-loss proxy and reliability</h3><table id="discomtable"></table>
</section>

<section class="tab" id="t-equity">
  <h2>Fair access: who gets the critical energy?</h2>
  <p class="sub">During a shortfall the controller serves every connected household the same critical energy before any household gets a second share. Larger homes therefore absorb the cut first.</p>
  <div class="w tall"><canvas id="equitychart"></canvas></div>
  <table id="equitytable"></table>
  <p class="small" id="fairness"></p>
</section>

<section class="tab" id="t-economics">
  <h2>Unit economics and affordability</h2>
  <div class="k" id="econkpis"></div>
  <div class="row"><div><h3>Sizing frontier</h3><div class="w"><canvas id="pareto"></canvas></div></div>
  <div><h3>Fee tiers</h3><table id="fees"></table>
  <p class="note" id="econnote"></p></div></div>
  <h3>Cost build-up per household</h3><table id="econtable"></table>
</section>

<section class="tab" id="t-whatif">
  <h2>What-if: size the battery for your feeder</h2>
  <p class="sub">Every point is a precomputed simulation, not an interpolation. Pick battery size, outage stress, cloudiness and e-rickshaw / 2W charging share.</p>
  <div class="row"><div><label class="small">Battery kWh</label><input id="wbat" type="range" min="0" max="100" step="1" value="36"><div class="small" id="wbatv"></div></div>
  <div><label class="small">Outage stress</label><input id="wout" type="range" min="0" max="100" step="1" value="50"><div class="small" id="woutv"></div></div></div>
  <div class="row"><div><label class="small">Cloudiness (PV share)</label><input id="wcloud" type="range" min="0" max="100" step="1" value="100"><div class="small" id="wcloudv"></div></div>
  <div><label class="small">EV / 2W charging share</label><input id="wev" type="range" min="0" max="100" step="1" value="0"><div class="small" id="wevv"></div></div></div>
  <div class="k" id="whtkpis"></div>
  <div class="w tall"><canvas id="whatif"></canvas></div>
  <h3>Day player</h3>
  <div class="row"><div><input id="player" type="range" min="0" max="95" step="1" value="44"><div class="small" id="playert"></div></div>
  <div><button id="playbtn">Play 24 h</button></div></div>
  <div class="w"><canvas id="flows"></canvas></div>
</section>

<section class="tab" id="t-method">
  <h2>Method, data and limitations</h2>
  <div id="method" class="small"></div>
  <h3>Every assumption, with its source</h3>
  <div style="overflow-x:auto"><table id="assumptions"></table></div>
</section>
</main>
<script>
const D=__DATA__, M=D.scenarios, f=(x,n=1)=>Number(x).toLocaleString(undefined,{minimumFractionDigits:n,maximumFractionDigits:n});
const SC={grid_only:['Grid only','#b3402f'],pv_batt_naive:['PV + battery, unmanaged','#8a8f98'],rule_reserve_tou:['Rule + reserve + solar DR','#c98b2e'],mpc_no_dr:['MPC, no demand response','#5b7fbf'],mpc_persistence:['MPC, persistence forecast','#7a5fa8'],mpc_full:['GridFlex','#1f7a4d'],oracle:['Oracle forecast','#0f5132']};
const C=()=>getComputedStyle(document.body).getPropertyValue('--fg').trim();
const mut=()=>getComputedStyle(document.body).getPropertyValue('--muted').trim();
Chart.defaults.color=C(); Chart.defaults.borderColor='rgba(130,150,140,.18)';
const L=(l,d,c,o={})=>({label:l,data:d,borderColor:c,backgroundColor:c,pointRadius:0,borderWidth:2,...o});
const base={responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false}};
const ax=(t)=>({scales:{y:{title:{display:!!t,text:t}},x:{ticks:{maxTicksLimit:12}}}});
const charts={};
function mk(id,cfg){const el=document.getElementById(id);if(!el)return;if(charts[id])charts[id].destroy();charts[id]=new Chart(el,cfg);return charts[id];}

document.getElementById('sub').textContent=`${D.meta.site} · ${D.meta.start} to ${D.meta.end} · ${D.meta.n_hh} homes · ${D.meta.pv_kwp} kWp PV · ${D.meta.bat_kwh} kWh battery · ${D.meta.test_days} held-out days`;
const tabs=[['overview','Overview'],['scenarios','Scenarios'],['discom','DISCOM'],['equity','Equity'],['economics','Economics'],['whatif','What-if'],['method','Method']];
document.getElementById('nav').innerHTML=tabs.map((t,i)=>`<button data-t="${t[0]}" class="${i?'':'on'}">${t[1]}</button>`).join('');
function show(name){document.querySelectorAll('.tab').forEach(e=>e.classList.toggle('on',e.id==='t-'+name));
 document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.t===name));draw[name]&&draw[name]();}
document.getElementById('nav').onclick=e=>{if(e.target.dataset.t)show(e.target.dataset.t)};

// ---------- KPIs ----------
const g=M.mpc_full,u=M.pv_batt_naive,q=M.grid_only,H=D.headline||{};
const hk=k=>H[k]?H[k].value:M.mpc_full[k];
const hsd=k=>H[k]&&H[k].seeds>1?` · ${H[k].seeds}-seed mean, single seed ${f(H[k].single_seed,2)}`:(H[k]?` · single seed`:'');
const kpi=(v,l)=>`<div class="c"><b>${v}</b><span>${l}</span></div>`;
document.getElementById('kpis').innerHTML=[
 kpi(f(hk('outage_hours_per_day'),2)+' h/day','critical supply interrupted'+hsd('outage_hours_per_day')+' · unmanaged '+f(u.outage_hours_per_day,2)+' · grid only '+f(q.outage_hours_per_day,2)),
 kpi(f(hk('evening_availability_pct'))+'%','evening 18–23 h availability'+hsd('evening_availability_pct')+' · unmanaged '+f(u.evening_availability_pct)+'%'),
 kpi(f(hk('critical_served_pct'))+'%','critical energy served'+hsd('critical_served_pct')+' · '+f(u.critical_served_pct)+'% unmanaged'),
 kpi(f(g.evening_peak_import_kw)+' kW','evening peak import · '+f(u.evening_peak_import_kw)+' kW unmanaged'),
 kpi(f(hk('bill_inr_per_hh_month'),0)+' ₹','grid bill per household/month'+hsd('bill_inr_per_hh_month')+' · '+f(u.bill_inr_per_hh_month,0)+' ₹ unmanaged'),
 kpi(f(g.curtailment_pct)+'%','solar curtailed · '+f(hk('self_consumption_pct'))+'% of PV self-consumed'+hsd('self_consumption_pct'))
].join('');

const cols=[['critical_served_pct','Critical energy served %','1'],['outage_hours_per_day','Interrupted critical h/day','2'],['evening_availability_pct','Evening availability %','1'],['unserved_critical_kwh_per_day','Unserved critical kWh/day','1'],['flex_served_pct','Flexible demand served %','1'],['curtailment_pct','Solar curtailed %','1'],['self_consumption_pct','PV self-consumed %','1'],['evening_peak_import_kw','Evening peak import kW','1'],['transformer_loading_pct','Transformer loading %','1'],['loss_pct','Technical-loss proxy %','2'],['bill_inr_per_hh_month','Grid bill ₹/hh/month','0'],['saidi_minutes_per_day','SAIDI-like min/day','0']];
document.getElementById('scen').innerHTML='<thead><tr><th>metric</th>'+D.modes.map(m=>`<th>${SC[m]?SC[m][0]:m}</th>`).join('')+'</tr></thead><tbody>'+
 cols.map(c=>`<tr><td>${c[1]}</td>`+D.modes.map(m=>`<td>${f(M[m][c[0]],+c[2])}</td>`).join('')+'</tr>').join('')+'</tbody>';

// ---------- day view ----------
const ds=document.getElementById('daysel');ds.innerHTML=D.days.map((d,i)=>`<option value="${i}">${d.label}</option>`).join('');
function pickDay(){const d=D.days[+ds.value];const X=d.load.map((_,i)=>String(Math.floor(i/4)).padStart(2,'0')+':'+String(i%4*15).padStart(2,'0'));
 mk('day1',{type:'line',data:{labels:X,datasets:[L('Load',d.load,'#5d6b62'),L('Solar',d.pv,'#e8a33d'),L('Grid import · GridFlex',d.g.mpc_full,'#1f7a4d'),L('Grid import · unmanaged',d.g.pv_batt_naive,'#8a8f98',{borderDash:[4,3]}),L('Feeder limit',d.cap,'#b3402f',{borderDash:[6,4],stepped:true})]},options:{...base,...ax('kW')}});
 mk('day2',{type:'line',data:{labels:X,datasets:[L('SOC · GridFlex',d.soc.mpc_full,'#1f7a4d',{fill:false}),L('SOC · unmanaged',d.soc.pv_batt_naive,'#8a8f98'),L('Unserved · GridFlex',d.shed.mpc_full,'#49b57e',{fill:true}),L('Unserved · unmanaged',d.shed.pv_batt_naive,'#b3402f',{fill:true})]},options:{...base,...ax('kWh / kW')}});
 const R=D.reasons.summary;
 document.getElementById('summary').innerHTML=Object.entries(R).map(([k,v])=>`<div><b>${k.replace(/_/g,' ')}</b>: ${v}</div>`).join('');
 document.getElementById('reasons').innerHTML=D.reasons.hourly.filter((x,i)=>i%4==0).slice(0,18).map(x=>`<li><b>${x.time}</b> ${x.text}</li>`).join('');
}
ds.onchange=pickDay;

// ---------- ablation ----------
function drawScen(){
 const names=D.modes.map(m=>SC[m][0]);
 mk('ablation',{type:'bar',data:{labels:names,datasets:[{label:'Interrupted critical hours/day',data:D.modes.map(m=>M[m].outage_hours_per_day),backgroundColor:D.modes.map(m=>SC[m][1])}]},options:{...base,...ax('h/day'),plugins:{legend:{display:false}}}});
 const rows=[['outage_hours_per_day','Interrupted h/day'],['evening_availability_pct','Evening availability %'],['unserved_critical_kwh_per_day','Unserved kWh/day'],['flex_served_pct','Flex served %'],['bill_inr_per_hh_month','Bill ₹/hh/month'],['curtailment_pct','Curtailed %']];
 document.getElementById('abtable').innerHTML='<thead><tr><th>scenario</th>'+rows.map(r=>`<th>${r[1]}</th>`).join('')+'</tr></thead><tbody>'+D.modes.map(m=>`<tr><td>${SC[m][0]}</td>`+rows.map(r=>`<td>${f(M[m][r[0]],2)}</td>`).join('')+'</tr>').join('')+'</tbody>';
 mk('billbars',{type:'bar',data:{labels:names,datasets:[{label:'₹ / household / month',data:D.modes.map(m=>M[m].bill_inr_per_hh_month),backgroundColor:D.modes.map(m=>SC[m][1])}]},options:{...base,...ax('₹/hh/month'),plugins:{legend:{display:false}}}});
 const ci=D.ci||{}, cmodes=Object.keys(ci);
 document.getElementById('cinote').textContent=cmodes.length?`Mean ± 95 % CI over ${ci[cmodes[0]]?ci[cmodes[0]].outage_hours_per_day.n:''} independent load/outage seeds on the same real weather.`:'Run with --seeds 20 to populate confidence intervals.';
 document.getElementById('citable').innerHTML=cmodes.length?'<thead><tr><th>metric</th>'+cmodes.map(m=>`<th>${SC[m]?SC[m][0]:m}</th>`).join('')+'</tr></thead><tbody>'+['outage_hours_per_day','evening_availability_pct','unserved_critical_kwh_per_day','bill_inr_per_hh_month'].map(k=>`<tr><td>${k.replace(/_/g,' ')}</td>`+cmodes.map(m=>{const c=ci[m][k];return c?`<td>${f(c.mean,2)} <span class="small">[${f(c.lo,2)}, ${f(c.hi,2)}]</span></td>`:'<td>–</td>';}).join('')+'</tr>').join('')+'</tbody>':'';
}

// ---------- discom ----------
function drawDiscom(){
 const X=D.discom.risk.prob.map((_,i)=>String(Math.floor(i/4)).padStart(2,'0')+':'+String(i%4*15).padStart(2,'0'));
 mk('risk',{type:'line',data:{labels:X,datasets:[L('P(outage or stress) %',D.discom.risk.prob.map(v=>100*v),'#b3402f',{fill:false}),L('Expected shortfall kW',D.discom.risk.expected_shortfall_kw,'#c98b2e'),L('Net load kW',D.discom.risk.net_load_kw,'#1f7a4d')]},options:{...base,...ax('% / kW')}});
 const d=D.days[+ds.value];
 mk('volt',{type:'line',data:{labels:d.v[0].map((_,i)=>String(Math.floor(i/4)).padStart(2,'0')+':'+String(i%4*15).padStart(2,'0')),datasets:d.v.map((v,b)=>L('branch '+(b+1),v,['#1f7a4d','#5b7fbf','#c98b2e'][b]))},options:{...base,...ax('pu'),scales:{y:{min:0.92,max:1.01}}}});
 const K=D.discom;
 document.getElementById('discomkpis').innerHTML=[
  kpi(f(K.peak_import_kw)+' kW','peak transformer import'),
  kpi(f(K.transformer_loading_pct)+'%','of transformer rating'),
  kpi(f(K.saidi_minutes_per_day,0)+' min/day','SAIDI-like interruption minutes'),
  kpi(f(K.voltage_min_pu,3)+' pu','minimum end-of-feeder voltage'),
  kpi(f(K.loss_pct,2)+'%','technical-loss proxy'),
  kpi(f(K.participating_homes,0),'homes providing flexibility')].join('');
 document.getElementById('actions').innerHTML=K.dr_actions.length?K.dr_actions.map(a=>`<li><b>#${a.rank} ${a.action}</b> — ${a.detail}<br><span class="small">${f(a.kw)} kW · ${f(a.kwh)} kWh this day · ₹${f(a.credit_inr,0)}/day · ${a.basis}</span></li>`).join(''):'<li>No dispatchable flexibility on this day.</li>';
 document.getElementById('discomtable').innerHTML='<tr><th>indicator</th><th>value</th></tr>'+[
  ['Evening peak import','kW',f(K.evening_peak_import_kw)],['Peak transformer loading','%',f(K.transformer_loading_pct)],
  ['Loss proxy','% delivered',f(K.loss_pct,2)],['Critical served','%',f(K.critical_served_pct)],
  ['Evening availability','%',f(K.evening_availability_pct)],['Voltage violations','steps',K.voltage_violations]
 ].map(r=>`<tr><td>${r[0]}</td><td>${r[2]} ${r[1]}</td></tr>`).join('');
}

// ---------- equity ----------
function drawEquity(){
 const names=Object.keys(D.equity.archetypes);
 mk('equitychart',{type:'bar',data:{labels:names.map(n=>n.replace('_',' ')),datasets:[{label:'Outage hours/day',data:names.map(n=>D.equity.archetypes[n].outage_hours_per_day),backgroundColor:'#1f7a4d'},{label:'Critical served %',data:names.map(n=>D.equity.archetypes[n].critical_served_pct),backgroundColor:'#8a8f98'}]},options:{...base,...ax('h/day · %')}});
 document.getElementById('equitytable').innerHTML='<thead><tr><th>archetype</th><th>homes</th><th>outage h/day</th><th>evening avail %</th><th>critical served %</th><th>served kWh/hh·day</th><th>PV+battery self-consumed %</th><th>unserved kWh/day</th></tr></thead><tbody>'+names.map(n=>`<tr><td>${n.replace('_',' ')}</td><td>${D.equity.archetypes[n].households}</td><td>${f(D.equity.archetypes[n].outage_hours_per_day,2)}</td><td>${f(D.equity.archetypes[n].evening_availability_pct)}</td><td>${f(D.equity.archetypes[n].critical_served_pct)}</td><td>${f(D.equity.archetypes[n].served_kwh_per_hh_day,2)}</td><td>${f(D.equity.archetypes[n].self_consumption_pct)}</td><td>${f(D.equity.archetypes[n].unserved_critical_kwh_per_day)}</td></tr>`).join('')+'</tbody>';
 const RU=D.equity.rules||{};
 document.getElementById('fairness').textContent=`Jain fairness index ${f(D.equity.fairness.jain_index,3)} on the served fraction of critical demand · low-income minus average served ${f(D.equity.fairness.low_income_gap_pp,2)} pp · rule: ${D.equity.fairness.rule}`+
  (RU.proportional?` · sensitivity: proportional-to-demand allocation gives Jain ${f(RU.proportional.fairness.jain_index,3)} and low-income ${f(RU.proportional.fairness.low_income_gap_pp,2)} pp (${f(RU.proportional.archetypes.low_income.critical_served_pct)}% vs ${f(RU.equal.archetypes.low_income.critical_served_pct)}% critical served)` : '');
}

// ---------- economics ----------
function drawEcon(){
 const E=D.econ;
 document.getElementById('econkpis').innerHTML=[
  kpi(f(E.capex_per_hh_inr,0)+' ₹','upfront capex per household'),
  kpi(f(E.annualised_cost_per_hh_month_inr,0)+' ₹','annualised cost per household/month'),
  kpi(f(E.bill_saving_vs_pv_battery_per_hh_month_inr,0)+' ₹','bill change vs same PV+battery, no control (negative = higher bill)'),
  kpi(f(E.net_value_per_hh_month_inr,0)+' ₹','net value per household/month (central)'),
  kpi(f(E.cost_per_kwh_critical_delivered_inr,2)+' ₹','cost per kWh of critical energy delivered'),
  kpi(f(E.breakeven_fee_per_hh_month_inr,0)+' ₹','break-even fee after reliability and DISCOM value')].join('');
 const pts=D.sizing.points||[];
 const key='net_cost_low_income_per_hh_month_inr';
 const dsFor=s=>({label:s+' tariff',data:pts.filter(p=>p.fee_scheme===s).map(p=>({x:p.outage_hours_per_day,y:p[key]})),backgroundColor:s==='lifeline'?'#1f7a4d':'#c98b2e',pointRadius:4});
 mk('pareto',{type:'scatter',data:{datasets:[dsFor('lifeline'),dsFor('flat'),{label:'knee',data:(D.sizing.knee?[{x:D.sizing.knee.outage_hours_per_day,y:D.sizing.knee[key]}]:[]),backgroundColor:'#b3402f',pointRadius:8}]},options:{...base,scales:{x:{title:{display:true,text:'interrupted critical h/day'}},y:{title:{display:true,text:'net cost, low-income ₹/hh/month'}}}}});
 const F=E.fee_tiers;
 document.getElementById('fees').innerHTML='<tr><th>tier</th><th>₹/month</th></tr>'+[['Low-income lifeline',F.lifeline_low_income_inr],['Standard',F.standard_inr],['Higher use',F.higher_use_inr],['Weighted fee income',F.collected_per_hh_month_inr],['Gross cost recovery %',F.gross_cost_recovery_pct]].map(r=>`<tr><td>${r[0]}</td><td>${f(r[1],r[0].includes('%')?0:0)}</td></tr>`).join('');
 document.getElementById('econnote').textContent=E.lifeline_note;
 document.getElementById('econtable').innerHTML='<tr><th>item</th><th>value</th></tr>'+Object.entries(E).filter(([k,v])=>typeof v==='number').map(([k,v])=>`<tr><td>${k.replace(/_/g,' ')}</td><td>${f(v,2)}</td></tr>`).join('');
}

// ---------- what-if ----------
const wb=document.getElementById('wbat'),wo=document.getElementById('wout'),wc=document.getElementById('wcloud'),we=document.getElementById('wev');
const near=(arr,v)=>arr.reduce((a,b)=>Math.abs(b-v)<Math.abs(a-v)?b:a,arr[0]);
function drawWhatif(){
 const all=(D.whatif&&D.whatif.results)||[];
 if(!all.length){document.getElementById('whtkpis').innerHTML='<div class="c"><span>What-if grid not built in this run (use the full run, not --quick).</span></div>';return;}
 const bats=[...new Set(all.map(p=>p.bat_kwh))].sort((a,b)=>a-b);
 const clouds=[...new Set(all.map(p=>p.pv_scale))].sort((a,b)=>a-b);
 const evs=[...new Set(all.map(p=>p.ev_scale))].sort((a,b)=>a-b);
 const bat=near(bats,bats[0]+(+wb.value/100)*(bats[bats.length-1]-bats[0]));
 const cloud=near(clouds,clouds[0]+(+wc.value/100)*(clouds[clouds.length-1]-clouds[0]));
 const ev=near(evs,evs[0]+(+we.value/100)*(evs[evs.length-1]-evs[0]));
 const stress=0.5+(+wo.value/100);
 document.getElementById('wbatv').textContent=bat+' kWh';
 document.getElementById('woutv').textContent=stress.toFixed(2)+'× outage stress';
 document.getElementById('wcloudv').textContent=Math.round(cloud*100)+'% of clear-sky PV';
 document.getElementById('wevv').textContent=ev.toFixed(1)+'× EV / 2W charging energy';
 const pts=all.filter(p=>p.bat_kwh===bat&&Math.abs(p.pv_scale-cloud)<1e-9&&Math.abs(p.ev_scale-ev)<1e-9).sort((a,b)=>a.outage_mult-b.outage_mult);
 if(!pts.length)return;
 const chosen=pts.reduce((best,p)=>Math.abs(p.outage_mult-stress)<Math.abs(best.outage_mult-stress)?p:best,pts[0]);
 document.getElementById('whtkpis').innerHTML=[
  kpi(f(chosen.outage_hours_per_day,2)+' h/day','interrupted critical supply'),
  kpi(f(chosen.evening_availability_pct)+'%','evening availability'),
  kpi(f(chosen.lifeline_availability_pct)+'%','lifeline-circuit availability'),
  kpi(f(chosen.bill_inr_per_hh_month,0)+' ₹','bill per household/month'),
  kpi(f(chosen.cost_per_hh_month_inr,0)+' ₹','annualised asset cost/household/month')].join('');
 mk('whatif',{type:'line',data:{labels:pts.map(p=>p.outage_mult.toFixed(2)+'×'),datasets:[L('Outage h/day',pts.map(p=>p.outage_hours_per_day),'#b3402f'),L('Lifeline availability %',pts.map(p=>p.lifeline_availability_pct/20),'#1f7a4d')]},options:{...base,...ax('h/day · (% ÷ 20)')}});
}
wb.oninput=wo.oninput=wc.oninput=we.oninput=drawWhatif;
let playing=null;
document.getElementById('playbtn').onclick=()=>{
 if(playing){clearInterval(playing);playing=null;document.getElementById('playbtn').textContent='Play 24 h';return;}
 document.getElementById('playbtn').textContent='Pause';
 playing=setInterval(()=>{const p=document.getElementById('player');p.value=(+p.value+1)%96;drawPlayer();},220);
};
function drawPlayer(){
 const i=+document.getElementById('player').value,d=D.days[+ds.value];
 document.getElementById('playert').textContent=`${String(Math.floor(i/4)).padStart(2,'0')}:${String(i%4*15).padStart(2,'0')} · load ${d.load[i]} kW · PV ${d.pv[i]} kW · grid ${d.g.mpc_full[i]} kW · SOC ${d.soc.mpc_full[i]} kWh`;
 mk('flows',{type:'bar',data:{labels:['PV','Grid','Battery','Load','Unserved'],datasets:[{label:'kW at '+document.getElementById('playert').textContent.split(' ·')[0],data:[d.pv[i],d.g.mpc_full[i],d.soc.mpc_full[i]/10,d.load[i],d.shed.mpc_full[i]],backgroundColor:['#e8a33d','#5b7fbf','#1f7a4d','#5d6b62','#b3402f']}]},options:{...base,...ax('kW'),plugins:{legend:{display:false}}}});
}
document.getElementById('player').oninput=drawPlayer;

// ---------- method ----------
document.getElementById('method').innerHTML=`
<p><b>What is simulated.</b> One 100 kVA distribution transformer serving ${D.meta.n_hh} homes with ${D.meta.pv_kwp} kWp of rooftop PV and a ${D.meta.bat_kwh} kWh / ${D.meta.bat_kw} kW shared battery. The controller re-solves a mixed-integer linear programme every hour over a 24 h horizon (96 × 15-min steps, open-source HiGHS) and executes the first steps, correcting in real time when the feeder limit binds.</p>
<p><b>Measured.</b> Interrupted critical-supply hours, evening (18–23 h) availability, unserved critical energy, flexible-load service, curtailment/export, transformer loading, a technical-loss proxy from a three-branch LinDistFlow feeder, and per-archetype reliability.</p>
<p><b>Real data.</b> ERA5 reanalysis irradiance and temperature (Open-Meteo archive), archived day-ahead operational forecasts with a 24 h lead (Open-Meteo previous-runs), PV modelled from real GHI and validated against PVGIS (${D.meta.provenance&&D.meta.provenance.pv_model?D.meta.provenance.pv_model.validation_pvgis.error_pct:'n/a'}% annual-yield error).</p>
<p><b>Calibrated / simulated.</b> Load shapes are calibrated to Telangana LT-I consumption and a published Indian residential shape; outages are drawn to reproduce CEEW's measured 3.5 outage h/day in notified town areas. Tariffs, costs and VoLL carry sourced ranges in the assumptions table.</p>
<p><b>Limitations.</b> No phase imbalance, no protection study, no hardware-in-the-loop; unannounced outages are not predictable and are handled by a reserve, not a forecast; second-life battery degradation and round-trip efficiency are simplified; the feeder topology is illustrative. These are stated, not hidden.</p>`;
document.getElementById('assumptions').innerHTML='<thead><tr><th>parameter</th><th>value</th><th>unit</th><th>kind</th><th>source</th><th>range</th></tr></thead><tbody>'+D.assumptions.map(a=>`<tr><td>${a.param}</td><td>${a.value}</td><td>${a.unit}</td><td>${a.kind}</td><td style="text-align:left">${a.source}</td><td>${a.range}</td></tr>`).join('')+'</tbody>';

const draw={overview:pickDay,scenarios:drawScen,discom:drawDiscom,equity:drawEquity,economics:drawEcon,whatif:()=>{drawWhatif();drawPlayer();},method:()=>{}};
pickDay();drawScen();drawWhatif();drawPlayer();
</script></body></html>"""
