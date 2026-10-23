"""The dashboard page: one self-contained HTML document, no network calls.

The page is kept apart from `report.py` so its design, copy and interaction can
change without touching the figures or the payload builder. `render()` fills
exactly two placeholders: the vendored Chart.js bundle and the results payload.
Everything else (type, palette, charts, microcopy) is in this file.

Design notes a maintainer should know
-------------------------------------
* Numbers are never typed into the prose. They arrive through `__DATA__` and are
  formatted once by `nf()`, so a rerun regenerates the page instead of drifting.
* Comparison figures use the 20-seed mean from `ci` when it is present and fall
  back to the single-seed scenario block, so two different bases are never
  compared in one sentence.
* Tabs are drawn lazily, on first activation. Chart.js sizes a canvas when it is
  created, and a hidden tab measures zero, so drawing every tab up front gave
  charts a wrong height until the next resize.
* The page is a file, not an app: hash routing, keyboard tab switching and a
  print stylesheet are the whole "routing" story.
"""
import json

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GridFlex · neighbourhood reliability dashboard</title>
<meta name="description" content="GridFlex: forecast-driven feeder reliability for a Hyderabad distribution transformer. Seven scenarios, real weather, one self-contained page.">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%2312684A'/%3E%3Cpath d='M18 6L9 18h5l-1 8 10-13h-5l1-7z' fill='%23fff'/%3E%3C/svg%3E">
<script src="chart.umd.min.js"></script>
<style>
:root{
  --paper:#F7F6F1; --surface:#FFFFFF; --surface-2:#F1EFE6;
  --ink:#121A17; --ink-2:#33413A; --muted:#586760;
  --line:#E4E1D6; --line-2:#CFCDBE;
  --green:#12684A; --pine:#0B3D2E; --mint:#4E9E7C;
  --amber:#C8871F; --amber-ink:#8A5A10;
  --clay:#A8422E; --blue:#3D6099; --blue-ink:#33517F;
  --violet:#6A5A93; --slate:#7C8781;
  --good-line:rgba(18,104,74,.28); --bad-line:rgba(168,66,46,.28); --warn-line:rgba(200,135,31,.34);
  --tint-green:rgba(18,104,74,.07); --tint-amber:rgba(200,135,31,.10);
  --tint-clay:rgba(168,66,46,.07); --tint-blue:rgba(61,96,153,.09);
  --shadow:0 1px 2px rgba(18,26,23,.04), 0 10px 26px -20px rgba(18,26,23,.45);
  --r:14px;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --serif:ui-serif,"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  --mono:ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --t-base:.94rem;
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#0E1513; --surface:#151E1A; --surface-2:#1B2521;
    --ink:#E9EFEA; --ink-2:#C3CFC8; --muted:#93A29B;
    --line:#24312B; --line-2:#33443C;
    --green:#59C795; --pine:#2F9169; --mint:#6FBF9C;
    --amber:#D9A04A; --amber-ink:#E4B567;
    --clay:#D4735B; --blue:#7C9DD6; --blue-ink:#A7C0E6;
    --violet:#A392CB; --slate:#8B9791;
    --good-line:rgba(89,199,149,.34); --bad-line:rgba(212,115,91,.34); --warn-line:rgba(217,160,74,.36);
    --tint-green:rgba(89,199,149,.10); --tint-amber:rgba(217,160,74,.12);
    --tint-clay:rgba(212,115,91,.10); --tint-blue:rgba(124,157,214,.12);
    --shadow:0 1px 2px rgba(0,0,0,.3), 0 12px 30px -22px rgba(0,0,0,.9);
  }
}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:var(--t-base)/1.62 var(--sans);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
h1,h2,h3,h4{margin:0;font-weight:600;letter-spacing:-.01em}
h2{font:600 clamp(1.35rem,2.4vw,1.72rem)/1.22 var(--serif);letter-spacing:-.018em}
h3{font-size:.96rem}
h4{font-size:.83rem;letter-spacing:.01em}
p{margin:0 0 10px}
code{font-family:var(--mono);font-size:.86em;background:var(--surface-2);padding:1px 5px;border-radius:4px}
.wrap{width:min(1148px,100% - 40px);margin-inline:auto}
@media(max-width:560px){.wrap{width:min(1148px,100% - 28px)}}
:focus-visible{outline:2px solid var(--green);outline-offset:2px;border-radius:6px}
.skip{position:absolute;left:-9999px;top:0;background:var(--surface);padding:8px 12px;border-radius:0 0 8px 0;z-index:60}
.skip:focus{left:0}

/* ---------- masthead ---------- */
.top{position:sticky;top:0;z-index:30;background:var(--paper);border-bottom:1px solid var(--line)}
.top-in{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:13px 0 11px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:11px;color:inherit;text-decoration:none;border:0}
.mark{width:34px;height:34px;border-radius:9px;background:var(--green);display:grid;place-items:center;flex:0 0 auto;
  box-shadow:0 1px 2px rgba(0,0,0,.18)}
.mark svg{width:17px;height:17px;display:block}
.brand b{display:block;font:600 1.01rem/1.15 var(--sans);letter-spacing:-.015em}
.brand em{display:block;font-style:normal;font-size:.73rem;color:var(--muted);margin-top:2px}
.top-meta{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.tabbar{display:flex;gap:0;overflow-x:auto;scrollbar-width:none;margin-top:1px}
.tabbar::-webkit-scrollbar{display:none}
.tabbtn{position:relative;border:0;background:transparent;padding:10px 13px 12px;font:500 .82rem/1 var(--sans);
  color:var(--muted);cursor:pointer;white-space:nowrap;display:flex;gap:7px;align-items:baseline;
  transition:color .18s ease}
.tabbtn .n{font:600 .61rem/1 var(--mono);color:var(--line-2);letter-spacing:.06em;transition:color .18s ease}
.tabbtn:hover{color:var(--ink)}
.tabbtn.on{color:var(--ink);font-weight:600}
.tabbtn.on .n{color:var(--green)}
.tabbtn::after{content:"";position:absolute;left:11px;right:11px;bottom:-1px;height:2px;border-radius:2px;
  background:var(--green);transform:scaleX(0);transform-origin:left;transition:transform .24s cubic-bezier(.2,.7,.3,1)}
.tabbtn.on::after{transform:scaleX(1)}

/* ---------- page ---------- */
main{padding:24px 0 60px;min-height:58vh}
.tab{display:none}
.tab.on{display:block;animation:rise .34s cubic-bezier(.22,.7,.3,1) both}
@keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
.sec-head{max-width:76ch;margin:2px 0 18px}
.sec-head h2{margin:8px 0 9px}
.eyebrow{font:600 .69rem/1.3 var(--sans);letter-spacing:.16em;text-transform:uppercase;color:var(--muted);
  display:flex;align-items:center;gap:8px}
.eyebrow::before{content:"";width:16px;height:1px;background:var(--line-2);flex:0 0 auto}
.lede{color:var(--muted);font-size:.92rem;margin:0;max-width:72ch}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:20px;
  box-shadow:var(--shadow);min-width:0}
.card+.card{margin-top:0}
.card-head{display:flex;align-items:baseline;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:12px}
.card-head .hint{margin-left:auto}
.hint{font-size:.77rem;color:var(--muted)}
.grid{display:grid;gap:16px}
.split{grid-template-columns:minmax(0,1.65fr) minmax(0,1fr)}
.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
.mt{margin-top:16px}
@media(max-width:880px){.split,.g2,.g3{grid-template-columns:minmax(0,1fr)}}

/* ---------- chips, badges ---------- */
.chip{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line-2);border-radius:999px;
  padding:3px 9px;font:600 .71rem/1.5 var(--sans);color:var(--ink-2);background:var(--surface);white-space:nowrap}
.chip.good{color:var(--green);border-color:var(--good-line);background:var(--tint-green)}
.chip.bad{color:var(--clay);border-color:var(--bad-line);background:var(--tint-clay)}
.chip.warn{color:var(--amber-ink);border-color:var(--warn-line);background:var(--tint-amber)}
.badge{display:inline-block;padding:2px 7px;border-radius:6px;font:600 .62rem/1.55 var(--sans);
  letter-spacing:.06em;text-transform:uppercase;white-space:nowrap}
.badge.real{background:var(--tint-green);color:var(--green)}
.badge.cited{background:var(--tint-blue);color:var(--blue-ink)}
.badge.assumption{background:var(--tint-amber);color:var(--amber-ink)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;vertical-align:1px}

/* ---------- hero ---------- */
.hero{display:flex;flex-direction:column;gap:10px;
  background:radial-gradient(115% 130% at 100% 0%,var(--tint-green) 0%,transparent 58%),var(--surface)}
.hero-top{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;flex-wrap:wrap}
.big{display:flex;align-items:baseline;gap:8px;margin:6px 0 2px;
  font:600 clamp(2.35rem,4.6vw,3.05rem)/.95 var(--mono);letter-spacing:-.045em;font-variant-numeric:tabular-nums}
.big .unit{font:500 .84rem/1 var(--sans);letter-spacing:0;color:var(--muted);transform:translateY(-3px)}
.hero-line{color:var(--muted);font-size:.88rem;margin:0;max-width:48ch}
.hero-line b{color:var(--ink-2);font-weight:600;font-family:var(--mono);font-size:.94em}
.ci{font:500 .73rem/1.6 var(--mono);color:var(--muted);letter-spacing:.005em;border-top:1px dashed var(--line);
  padding-top:9px;margin-top:auto}

/* ---------- hero grid + glance strip ---------- */
.hero-grid{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,1fr);gap:30px;align-items:start}
.hero-main{display:flex;flex-direction:column;min-width:0}
.hero-side{border-left:1px solid var(--line);padding-left:28px;min-width:0}
@media(max-width:900px){
  .hero-grid{grid-template-columns:minmax(0,1fr);gap:20px}
  .hero-side{border-left:0;padding-left:0;border-top:1px solid var(--line);padding-top:18px}
}
.statstrip{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-top:16px}
@media(max-width:1120px){.statstrip{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:620px){.statstrip{grid-template-columns:repeat(2,minmax(0,1fr))}}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 15px;
  box-shadow:var(--shadow);min-width:0}
.stat b{display:block;font:600 1.3rem/1.15 var(--mono);letter-spacing:-.02em;
  font-variant-numeric:tabular-nums;color:var(--ink)}
.stat span{display:block;font-size:.71rem;line-height:1.4;color:var(--muted);margin-top:4px}
.stat em{display:block;font:600 .68rem/1.45 var(--sans);font-style:normal;margin-top:7px}
.stat em.good{color:var(--green)}
.stat em.bad{color:var(--clay)}

/* ---------- reliability ladder ---------- */
.ladder{display:grid;gap:11px}
.rung{display:grid;grid-template-columns:minmax(96px,1.35fr) minmax(0,1fr) 56px;gap:12px;align-items:center}
.rung .lbl{font-size:.79rem;color:var(--ink-2);display:flex;align-items:center;gap:7px;min-width:0}
.rung .lbl i{width:9px;height:9px;border-radius:2px;flex:0 0 auto;display:inline-block}
.rung .track{position:relative;height:24px;border-radius:6px;background:var(--surface-2)}
.rung .fill{position:absolute;left:0;top:0;bottom:0;border-radius:6px;min-width:3px;
  transition:width .7s cubic-bezier(.2,.7,.3,1)}
.rung .val{font:600 .95rem/1 var(--mono);font-variant-numeric:tabular-nums;text-align:right}
.rung .val span{display:block;font:400 .66rem/1.5 var(--sans);color:var(--muted);letter-spacing:.03em}
.rung.lead .lbl{font-weight:600;color:var(--ink)}
.rung.lead .val{color:var(--green)}
@media(max-width:720px){
  .rung{grid-template-columns:minmax(0,1fr) 62px;row-gap:6px}
  .rung .track{grid-column:1/-1;order:3}
}

/* ---------- plots ---------- */
.plot{position:relative;height:240px;min-width:0}
.plot.tall{height:300px}
.plot.short{height:196px}
.plot+.plot{margin-top:14px}

/* ---------- day view ---------- */
.daymeta{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 4px}
.facts-mini{display:flex;gap:20px;flex-wrap:wrap}
.facts-mini div{font-size:.72rem;color:var(--muted);letter-spacing:.01em}
.facts-mini b{display:block;font:600 .94rem/1.4 var(--mono);color:var(--ink);letter-spacing:0}
.ribbon{display:grid;grid-template-columns:repeat(96,1fr);gap:2px;margin:10px 0 6px}
.ribbon i{display:block;height:18px;border-radius:2px;background:var(--surface-2)}
.ribbon i.normal{background:rgba(78,158,124,.35)}
.ribbon i.evening{background:rgba(61,96,153,.42)}
.ribbon i.stress{background:var(--amber)}
.ribbon i.island{background:var(--clay)}
.ribbon-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:.71rem;color:var(--muted);margin-bottom:6px}
.ribbon-legend span{display:inline-flex;align-items:center;gap:6px}
.ribbon-legend i{width:9px;height:9px;border-radius:2px;display:inline-block}
.narrative{margin-top:18px}
.narrative h4{margin-bottom:8px}
.events{list-style:none;margin:0;padding:0;max-height:300px;overflow:auto;border-top:1px solid var(--line)}
.events li{display:grid;grid-template-columns:50px minmax(0,1fr);gap:10px;padding:7px 2px;align-items:baseline;
  border-bottom:1px dashed var(--line);font-size:.79rem;color:var(--ink-2)}
.events .t{font:600 .72rem/1.5 var(--mono);color:var(--muted)}
.events li.alert .t{color:var(--clay)}
.events li.alert span:last-child{color:var(--ink)}
.fact-list{margin:0;display:grid}
.fact-list div{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-top:1px solid var(--line);font-size:.79rem}
.fact-list div:first-child{border-top:0}
.fact-list span{color:var(--muted)}
.fact-list b{font:600 .8rem/1.5 var(--mono);font-variant-numeric:tabular-nums}

/* ---------- tables ---------- */
.scroll{overflow-x:auto;margin:0 -4px;padding:0 4px}
.tbl{width:100%;border-collapse:collapse;font-size:.82rem;font-variant-numeric:tabular-nums}
.tbl th{font:600 .67rem/1.3 var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  text-align:right;padding:0 10px 8px;border-bottom:1px solid var(--line-2);white-space:nowrap}
.tbl td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl td.n{font-family:var(--mono)}
.tbl td.src{white-space:normal;min-width:220px;color:var(--muted);font-size:.76rem;line-height:1.45}
.tbl tbody tr:hover{background:var(--surface-2)}
.tbl tr.me td{background:var(--tint-green)}
.tbl tr.me td:first-child{font-weight:600}
.tbl caption{caption-side:top;text-align:left;font-size:.74rem;color:var(--muted);padding-bottom:8px}

/* ---------- CI ranges ---------- */
.cirange{display:grid;gap:9px;margin:8px 0 16px}
.cirange .row{display:grid;grid-template-columns:180px minmax(0,1fr) 150px;gap:12px;align-items:center}
.cirange .name{font-size:.79rem;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cirange .track{position:relative;height:8px;border-radius:99px;background:var(--surface-2)}
.cirange .band{position:absolute;top:0;bottom:0;border-radius:99px;opacity:.85}
.cirange .mean{position:absolute;top:-3px;width:3px;height:14px;border-radius:2px;background:var(--ink);transform:translateX(-1px)}
.cirange .num{font:500 .73rem/1.4 var(--mono);color:var(--muted);text-align:right}
@media(max-width:700px){.cirange .row{grid-template-columns:1fr;gap:4px}.cirange .num{text-align:left}}

/* ---------- DISCOM ---------- */
.heat{display:grid;grid-template-columns:repeat(24,minmax(30px,1fr));gap:3px}
.heat .cell{border-radius:6px;padding:6px 5px;min-height:56px;display:flex;flex-direction:column;
  justify-content:space-between;border:1px solid var(--line)}
.heat .h{font:600 .59rem/1 var(--mono);color:var(--muted);letter-spacing:.02em}
.heat .p{font:600 .71rem/1 var(--mono)}
.heat-legend{display:flex;align-items:center;gap:9px;font-size:.71rem;color:var(--muted);margin-top:10px;flex-wrap:wrap}
.heat-legend .bar{width:96px;height:7px;border-radius:99px;background:linear-gradient(90deg,rgba(168,66,46,.10),var(--clay))}
.actions{display:grid;gap:10px}
.action{display:grid;grid-template-columns:30px minmax(0,1fr) auto;gap:12px;padding:13px 14px;
  border:1px solid var(--line);border-radius:12px;background:var(--surface-2)}
.action .rank{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;
  font:600 .73rem/1 var(--mono);background:var(--ink);color:var(--paper)}
.action .title{font-weight:600;font-size:.855rem;line-height:1.35}
.action .detail{font-size:.775rem;color:var(--muted);margin-top:3px}
.action .basis{font-size:.72rem;color:var(--muted);margin-top:5px;font-style:italic}
.action .credit{font:600 .92rem/1.1 var(--mono);text-align:right;color:var(--green)}
.action .credit span{display:block;font:400 .67rem/1.5 var(--sans);color:var(--muted);margin-top:4px}
.meter{height:6px;border-radius:99px;background:var(--surface-2);overflow:hidden;margin-top:8px}
.meter i{display:block;height:100%;border-radius:99px;background:var(--green);transition:width .6s ease}
.action .meter{background:var(--line)}

/* ---------- equity ---------- */
.arch h4{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:7px}
.arch .hh{font:600 1.5rem/1 var(--mono);letter-spacing:-.02em}
.arch .hs{font-size:.73rem;color:var(--muted);margin:4px 0 14px}
.arch .m{margin-bottom:12px}
.arch .m .top{display:flex;justify-content:space-between;align-items:baseline;gap:8px;
  font-size:.74rem;color:var(--ink-2);margin-bottom:5px}
.arch .m .top b{font-family:var(--mono);font-size:.79rem;font-variant-numeric:tabular-nums}
.bigindex{font:600 2.1rem/1 var(--mono);letter-spacing:-.03em;color:var(--green);margin:6px 0 2px}
.bigindex span{font:400 .72rem/1 var(--sans);color:var(--muted);letter-spacing:0;margin-left:6px}

/* ---------- economics ---------- */
.ledger{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:26px}
.led{display:grid}
.led .row{display:grid;grid-template-columns:1fr auto;gap:10px;padding:8px 0;border-top:1px dashed var(--line);font-size:.82rem}
.led .row:first-of-type{border-top:0}
.led .row b{font:600 .85rem/1.4 var(--mono);font-variant-numeric:tabular-nums}
.led .row b.neg{color:var(--clay)}
.led .row b.pos{color:var(--green)}
.led h4{margin-bottom:4px;display:flex;align-items:center;gap:7px}
.netrow{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-top:16px;
  padding-top:14px;border-top:1px solid var(--line-2);flex-wrap:wrap}
.netrow .lbl{font-size:.8rem;color:var(--muted)}
.netrow b{font:600 1.55rem/1 var(--mono);letter-spacing:-.02em;color:var(--green)}
.rangetrack{position:relative;height:9px;border-radius:99px;background:var(--surface-2);margin:14px 0 4px}
.rangetrack .zero{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--line-2);border-radius:2px}
.rangetrack .rng{position:absolute;top:0;bottom:0;border-radius:99px;background:var(--tint-green);border:1px solid var(--good-line)}
.rangetrack .pin{position:absolute;top:-4px;width:3px;height:17px;border-radius:2px;background:var(--green)}
.rangelabels{display:flex;justify-content:space-between;font:500 .7rem/1.4 var(--mono);color:var(--muted)}
.tiers{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:10px 0 4px}
.tier{border:1px solid var(--line);border-radius:11px;padding:12px 13px;background:var(--surface-2)}
.tier b{display:block;font:600 1.18rem/1 var(--mono);margin:7px 0 3px}
.tier span{font-size:.71rem;color:var(--muted)}
.tier.free{border-color:var(--good-line);background:var(--tint-green)}
.tier.free b{color:var(--green)}

/* ---------- what-if ---------- */
.ctrl{display:grid;grid-template-columns:148px minmax(0,1fr);gap:14px;align-items:center;padding:10px 0;
  border-top:1px solid var(--line)}
.ctrl:first-child{border-top:0;padding-top:2px}
.ctrl label,.ctrl .lbl{font-size:.78rem;color:var(--ink-2);font-weight:500}
.ctrl .seg{justify-self:start}
.seg{display:inline-flex;background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:3px;gap:2px;flex-wrap:wrap}
.seg button{border:0;background:transparent;color:var(--ink-2);font:500 .755rem/1 var(--sans);
  padding:7px 11px;border-radius:7px;cursor:pointer;white-space:nowrap;transition:background .16s ease,color .16s ease}
.seg button:hover{color:var(--ink)}
.seg button[aria-pressed=true]{background:var(--surface);color:var(--ink);font-weight:600;box-shadow:0 1px 3px rgba(18,26,23,.14)}
@media(max-width:700px){.ctrl{grid-template-columns:minmax(0,1fr)}}
.console{background:#0C1411;border:1px solid #1D2A25;border-radius:var(--r);padding:20px;color:#E9F1EC;
  box-shadow:var(--shadow)}
.console .eyebrow{color:#93A89E}
.console .eyebrow::before{background:#2C3D36}
.console h3{color:#fff;margin-top:6px;font-size:1.02rem}
.console .card-head{border-bottom:1px solid rgba(233,241,236,.12);padding-bottom:12px}
.console .hint{color:#93A89E}
.clock{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:12px 0 4px}
.clock b{font:600 2.15rem/1 var(--mono);letter-spacing:-.03em;color:#fff;font-variant-numeric:tabular-nums}
.clock .soc{font:500 .74rem/1.5 var(--mono);color:#93A89E}
.controls{display:grid;grid-template-columns:108px minmax(0,1fr);gap:16px;align-items:center;margin:6px 0 12px}
@media(max-width:620px){.controls{grid-template-columns:minmax(0,1fr)}}
.player-facts{display:flex;gap:20px;flex-wrap:wrap;margin:4px 0 14px}
.player-facts div{font-size:.66rem;color:#93A89E;text-transform:uppercase;letter-spacing:.09em}
.player-facts b{display:block;font:600 .94rem/1.5 var(--mono);color:#E9F1EC;letter-spacing:0;text-transform:none}
.btn{border:1px solid var(--line-2);background:var(--surface);color:var(--ink);border-radius:9px;
  padding:7px 13px;font:600 .775rem/1.2 var(--sans);cursor:pointer;
  transition:background .16s ease,transform .12s ease}
.btn:hover{background:var(--surface-2)}
.btn:active{transform:translateY(1px)}
.console .btn{background:rgba(255,255,255,.07);border-color:rgba(255,255,255,.22);color:#fff}
.console .btn:hover{background:rgba(255,255,255,.13)}
.linkbtn{border:0;background:none;padding:0;color:var(--green);font:inherit;font-weight:600;
  cursor:pointer;border-bottom:1px solid var(--good-line)}
select{appearance:none;-webkit-appearance:none;background:var(--surface);border:1px solid var(--line-2);
  border-radius:9px;padding:7px 30px 7px 11px;font:500 .8rem/1.4 var(--sans);color:var(--ink);cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23586760' fill='none' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 10px center}
.console select{background-color:#131E19;border-color:rgba(233,241,236,.22);color:#E9F1EC}
input[type=range]{-webkit-appearance:none;appearance:none;width:100%;height:26px;background:transparent;cursor:pointer}
input[type=range]::-webkit-slider-runnable-track{height:4px;border-radius:99px;background:var(--track,var(--surface-2))}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:15px;height:15px;border-radius:50%;
  background:var(--surface);border:2px solid var(--green);margin-top:-5.5px;box-shadow:0 1px 3px rgba(0,0,0,.25)}
input[type=range]::-moz-range-track{height:4px;border-radius:99px;background:var(--track,var(--surface-2))}
input[type=range]::-moz-range-thumb{width:12px;height:12px;border-radius:50%;background:var(--surface);
  border:2px solid var(--green)}
.console input[type=range]{--track:rgba(255,255,255,.18)}
.console input[type=range]::-webkit-slider-thumb{background:#0C1411;border-color:#7FD3A8}
.console input[type=range]::-moz-range-thumb{background:#0C1411;border-color:#7FD3A8}

/* ---------- method ---------- */
.prov h4{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.prov ul{margin:0;padding-left:16px}
.prov li{font-size:.79rem;color:var(--ink-2);margin:5px 0;line-height:1.5}
.prov li span{color:var(--muted)}
.statline{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:10px}
.statline div{background:var(--surface-2);border-radius:10px;padding:10px 12px}
.statline b{display:block;font:600 .98rem/1.3 var(--mono)}
.statline span{font-size:.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;line-height:1.4;display:block}
@media(max-width:700px){.statline{grid-template-columns:repeat(2,minmax(0,1fr))}}
.steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;counter-reset:s}
.step{position:relative;padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--surface-2)}
.step::before{counter-increment:s;content:counter(s,decimal-leading-zero);font:600 .68rem/1 var(--mono);
  color:var(--green);letter-spacing:.08em}
.step b{display:block;margin:8px 0 4px;font-size:.85rem}
.step p{font-size:.755rem;color:var(--muted);margin:0;line-height:1.5}
@media(max-width:880px){.steps{grid-template-columns:repeat(2,minmax(0,1fr))}}
.limits{display:grid;counter-reset:l}
.limits div{display:grid;grid-template-columns:28px minmax(0,1fr);gap:10px;padding:10px 0;
  border-top:1px solid var(--line);font-size:.82rem;color:var(--ink-2);line-height:1.55}
.limits div::before{counter-increment:l;content:counter(l,decimal-leading-zero);font:600 .68rem/1.9 var(--mono);
  color:var(--clay)}
.filter{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.filter button{border:1px solid var(--line-2);background:var(--surface);color:var(--ink-2);
  border-radius:999px;padding:4px 11px;font:600 .71rem/1.5 var(--sans);cursor:pointer}
.filter button[aria-pressed=true]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.filter button span{opacity:.65;margin-left:4px;font-weight:500}

/* ---------- empty + footer ---------- */
.empty{max-width:54ch;margin:56px auto;text-align:center}
.empty .mark{width:46px;height:46px;margin:0 auto 18px;border-radius:12px}
.empty h2{margin-bottom:10px}
.empty p{color:var(--muted);font-size:.9rem}
.empty .hint{display:block;margin-top:14px}
.empty-inline{border:1px dashed var(--line-2);border-radius:12px;padding:18px;color:var(--muted);
  font-size:.82rem;background:var(--surface-2)}
footer{border-top:1px solid var(--line);padding:18px 0 44px;color:var(--muted);font-size:.74rem}
footer .in{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;align-items:baseline}
footer code{font-size:.72rem}
noscript{display:block;padding:16px;background:var(--tint-amber);border-bottom:1px solid var(--warn-line);font-size:.85rem}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
}
@media print{
  .top{position:static}
  .tabbar,.no-print{display:none!important}
  .tab{display:block!important;page-break-inside:avoid;margin-bottom:20px}
  .card{box-shadow:none;border-color:#ccc}
  .plot{height:190px}
  body{background:#fff;font-size:10.5pt}
  .console{background:#fff;color:#111;border-color:#ccc}
  .console h3,.clock b{color:#111}
  .console .eyebrow,.console .hint,.clock .soc,.player-facts div{color:#555}
  .player-facts b{color:#111}
  footer{padding-bottom:8px}
}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<noscript>This dashboard draws its charts from a results payload embedded in the file. It needs JavaScript; the numbers are also in <code>outputs/results.json</code>.</noscript>
<header class="top">
  <div class="wrap top-in">
    <a class="brand" href="#overview">
      <span class="mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="M18 4L8 18h6l-1 10L24 13h-6l1-9z" fill="#fff"/></svg></span>
      <span><b>GridFlex</b><em id="sitemeta">neighbourhood reliability</em></span>
    </a>
    <div class="top-meta">
      <span class="chip good">real weather</span>
      <span class="chip good">real day-ahead forecast</span>
      <span class="chip warn">simulated outages</span>
    </div>
  </div>
  <div class="wrap"><nav class="tabbar" id="nav" role="tablist" aria-label="Dashboard sections"></nav></div>
</header>

<main id="main">
  <div class="wrap">

  <section class="tab" id="t-overview" role="tabpanel" aria-labelledby="b-overview" tabindex="-1">
    <div class="sec-head">
      <div class="eyebrow">Reliability</div>
      <h2>Did the neighbourhood stay supplied?</h2>
      <p class="lede">Seven scenarios, one plant: the same 100&nbsp;kVA transformer, the same real Hyderabad weather and the same load and outage draws. Only the control software changes.</p>
    </div>
    <div class="card hero" id="hero"></div>
    <div class="statstrip" id="glance"></div>
    <p class="hint" style="margin:10px 2px 0">Compared with the same PV and battery left uncontrolled. The bill rises because more critical energy is actually delivered; the Economics tab prices that trade.</p>
    <div class="card mt">
      <div class="card-head">
        <h3>One held-out day, quarter by quarter</h3>
        <span class="hint">pick a day to inspect</span>
        <select id="daysel" aria-label="Held-out day"></select>
      </div>
      <div class="daymeta" id="daymeta"></div>
      <div class="ribbon-legend">
        <span><i style="background:rgba(78,158,124,.45)"></i>normal</span>
        <span><i style="background:rgba(61,96,153,.55)"></i>evening allocation</span>
        <span><i style="background:var(--amber)"></i>DISCOM stress</span>
        <span><i style="background:var(--clay)"></i>feeder off</span>
      </div>
      <div class="ribbon" id="ribbon" aria-hidden="true"></div>
      <div class="plot tall"><canvas id="day1" role="img" aria-label="Load, solar, grid import and feeder limit over the selected day"></canvas></div>
      <div class="plot"><canvas id="day2" role="img" aria-label="Battery state of charge and unserved critical energy over the selected day"></canvas></div>
      <div class="grid g2 narrative">
        <div>
          <h4>What happened that day</h4>
          <div class="fact-list" id="summary"></div>
        </div>
        <div>
          <h4>Why the controller acted <span class="hint" id="reasonday"></span></h4>
          <div class="hint" id="reasonhint"></div>
          <ol class="events" id="reasons"></ol>
        </div>
      </div>
    </div>
  </section>

  <section class="tab" id="t-scenarios" role="tabpanel" aria-labelledby="b-scenarios" tabindex="-1">
    <div class="sec-head">
      <div class="eyebrow">Ablation</div>
      <h2>Which component earns the gain?</h2>
      <p class="lede">Same hardware, same weather, same draws. Each row switches off one piece of the machinery — forecasting, flexible loads, the optimiser itself — so the gain can be attributed instead of asserted.</p>
    </div>
    <div class="card">
      <div class="card-head"><h3>Interrupted critical hours per day</h3><span class="hint">lower is better</span></div>
      <div class="plot tall"><canvas id="ablation" role="img" aria-label="Ranked bar chart of interrupted critical hours per day by scenario"></canvas></div>
      <p class="hint" id="ablatenote" style="margin-top:10px"></p>
    </div>
    <div class="card mt">
      <div class="card-head"><h3>Every scenario, side by side</h3><span class="hint">same draws, same weather</span></div>
      <div class="scroll"><table class="tbl" id="abtable"></table></div>
    </div>
    <div class="card mt">
      <div class="card-head"><h3>The bill each scenario buys</h3><span class="hint">₹ per household per month</span></div>
      <div class="plot"><canvas id="billbars" role="img" aria-label="Bar chart of monthly household grid bill by scenario"></canvas></div>
      <p class="hint" style="margin-top:8px">A higher bill is not a defect: it is more critical energy actually delivered. The Economics tab prices the reliability that buys.</p>
    </div>
    <div class="card mt">
      <div class="card-head"><h3>Confidence intervals</h3><span class="hint" id="cibadge"></span></div>
      <p class="hint" id="cinote"></p>
      <div class="cirange" id="cirange"></div>
      <div class="scroll"><table class="tbl" id="citable"></table></div>
    </div>
  </section>

  <section class="tab" id="t-discom" role="tabpanel" aria-labelledby="b-discom" tabindex="-1">
    <div class="sec-head">
      <div class="eyebrow">Distribution operator</div>
      <h2>What the feeder engineer sees</h2>
      <p class="lede">The same day the neighbourhood lives through, from the other side of the meter: when the transformer is at risk, what a stress window costs, and which actions a DISCOM could pay for.</p>
    </div>
    <div class="card">
      <div class="card-head"><h3>Indicators for the selected feeder day</h3><span class="hint" id="discomday"></span></div>
      <div class="grid g3" id="discomkpis" style="gap:10px"></div>
    </div>
    <div class="card mt">
      <div class="card-head"><h3>Feeder risk by hour</h3><span class="hint">modelled probability of an outage or announced stress window</span></div>
      <div class="scroll"><div class="heat" id="heat"></div></div>
      <div class="heat-legend"><span>0%</span><span class="bar"></span><span>100%</span><span style="margin-left:6px">darker = more likely</span></div>
    </div>
    <div class="grid g2 mt">
      <div class="card">
        <div class="card-head"><h3>Expected shortfall and net load</h3></div>
        <div class="plot"><canvas id="risk" role="img" aria-label="Expected shortfall, net load and import cap over the day"></canvas></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>End-of-feeder voltage</h3><span class="hint" id="voltnote"></span></div>
        <div class="plot"><canvas id="volt" role="img" aria-label="Voltage at three points along the feeder"></canvas></div>
      </div>
    </div>
    <div class="card mt">
      <div class="card-head"><h3>Ranked demand-response actions</h3><span class="hint">credit is the modelled value of the action on this day</span></div>
      <div class="actions" id="actions"></div>
    </div>
    <div class="card mt">
      <div class="card-head"><h3>Losses and reliability</h3></div>
      <div class="scroll"><table class="tbl" id="discomtable"></table></div>
    </div>
  </section>

  <section class="tab" id="t-equity" role="tabpanel" aria-labelledby="b-equity" tabindex="-1">
    <div class="sec-head">
      <div class="eyebrow">Fair access</div>
      <h2>Who gets the critical energy?</h2>
      <p class="lede">During a shortfall the controller serves every connected household the same share of its critical demand before any household gets a second share. Larger homes therefore absorb the cut first — deliberately.</p>
    </div>
    <div class="grid g3" id="archcards"></div>
    <div class="grid split mt">
      <div class="card">
        <div class="card-head"><h3>Fairness under the rule the controller uses</h3></div>
        <div class="bigindex" id="jain"></div>
        <p class="hint" id="jainnote"></p>
        <div class="plot short" style="margin-top:12px"><canvas id="equitychart" role="img" aria-label="Unserved critical energy per day by household archetype"></canvas></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>If the rule were proportional to demand</h3></div>
        <div id="rulesens"></div>
      </div>
    </div>
    <div class="card mt">
      <div class="card-head"><h3>All archetype metrics</h3></div>
      <div class="scroll"><table class="tbl" id="equitytable"></table></div>
    </div>
  </section>

  <section class="tab" id="t-economics" role="tabpanel" aria-labelledby="b-economics" tabindex="-1">
    <div class="sec-head">
      <div class="eyebrow">Unit economics</div>
      <h2>What it costs, and what it returns</h2>
      <p class="lede">Reliability is not free and it is not the only line. This is the ledger a resident committee would actually argue over, with the assumption ranges kept visible.</p>
    </div>
    <div class="grid g3" id="econkpis" style="gap:10px"></div>
    <div class="card mt">
      <div class="card-head"><h3>Monthly ledger per household</h3><span class="hint">central case · same PV and battery, with and without control</span></div>
      <div class="ledger" id="ledger"></div>
      <div class="rangetrack" id="netrange"></div>
      <div class="rangelabels" id="netrangelabels"></div>
    </div>
    <div class="grid split mt">
      <div class="card">
        <div class="card-head"><h3>Battery sizing frontier</h3><span class="hint" id="kneenote"></span></div>
        <div class="plot tall"><canvas id="pareto" role="img" aria-label="Net cost against interrupted hours for each battery size and tariff"></canvas></div>
        <div class="fact-list" id="kneefacts" style="margin-top:10px"></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>Who pays what</h3></div>
        <div class="tiers" id="tiers"></div>
        <p class="hint" id="tiernote"></p>
      </div>
    </div>
    <div class="card mt">
      <div class="card-head"><h3>Cost build-up and delivery</h3></div>
      <div class="scroll"><table class="tbl" id="econtable"></table></div>
    </div>
  </section>

  <section class="tab" id="t-whatif" role="tabpanel" aria-labelledby="b-whatif" tabindex="-1">
    <div class="sec-head">
      <div class="eyebrow">Sizing</div>
      <h2>Size it for your own feeder</h2>
      <p class="lede">These are precomputed simulations, not a fitted curve: every combination below was re-run end to end. Pick a configuration and the numbers move to a case that was actually simulated.</p>
    </div>
    <div class="card">
      <div class="card-head"><h3>Configuration</h3><span class="hint" id="whatiffixed"></span></div>
      <div id="whatifbody">
        <div class="ctrl"><span class="lbl">Battery size</span><div class="seg" id="seg-bat" role="group" aria-label="Battery size"></div></div>
        <div class="ctrl"><span class="lbl">Outage stress</span><div class="seg" id="seg-om" role="group" aria-label="Outage stress multiplier"></div></div>
        <div class="ctrl"><span class="lbl">Solar resource</span><div class="seg" id="seg-pv" role="group" aria-label="Solar resource level"></div></div>
        <div class="ctrl"><span class="lbl">EV / 2W charging</span><div class="seg" id="seg-ev" role="group" aria-label="EV and two-wheeler charging energy"></div></div>
        <p class="hint" style="margin:12px 0 0">Only combinations that were simulated are offered. Nothing on this page interpolates between runs.</p>
      </div>
    </div>
    <div class="card mt">
      <div class="card-head"><h3>Result of this configuration</h3><span class="hint" id="whatifdelta"></span></div>
      <div class="grid g3" id="whtkpis" style="gap:10px"></div>
      <div class="plot tall" style="margin-top:16px"><canvas id="whatif" role="img" aria-label="Interrupted hours and lifeline availability against battery size"></canvas></div>
    </div>
    <div class="mt">
      <div class="console">
        <div class="card-head">
          <div><div class="eyebrow">Day player</div><h3>Walk through a day, quarter by quarter</h3></div>
          <select id="pdaysel" aria-label="Day for the player"></select>
        </div>
        <div class="clock"><b id="clock">11:00</b><span class="soc" id="socread"></span></div>
        <div class="controls">
          <button id="playbtn" class="btn" type="button">Play 24 h</button>
          <input id="player" type="range" min="0" max="95" step="1" value="44" aria-label="Time of day">
        </div>
        <div class="player-facts" id="playerfacts"></div>
        <div class="plot short"><canvas id="flows" role="img" aria-label="Flows at the selected quarter hour"></canvas></div>
      </div>
    </div>
  </section>

  <section class="tab" id="t-method" role="tabpanel" aria-labelledby="b-method" tabindex="-1">
    <div class="sec-head">
      <div class="eyebrow">Method, data, limits</div>
      <h2>What is measured, what is modelled, what is assumed</h2>
      <p class="lede">The dashboard is only useful if a judge can see where each number comes from. Real observations are labelled real; assumptions carry a source and a range and are never presented as measurements.</p>
    </div>
    <div class="grid g3" id="provcards"></div>
    <div class="card mt">
      <div class="card-head"><h3>How a decision is made</h3><span class="hint">re-solved hourly on a 24 h horizon, 15-minute steps</span></div>
      <div class="steps">
        <div class="step"><b>Forecast</b><p>Day-ahead PV and load with quantiles, corrected against the previous day's error.</p></div>
        <div class="step"><b>Optimise</b><p>Mixed-integer programme over a 24 h horizon: battery, import cap, voltage band, flexible windows, outage reserve.</p></div>
        <div class="step"><b>Execute</b><p>Apply the first hour. If the feeder limit binds, re-solve and correct in real time.</p></div>
        <div class="step"><b>Fall back</b><p>If the optimiser or network is unavailable, hold reserve and protect the lifeline circuit.</p></div>
      </div>
    </div>
    <div class="grid split mt">
      <div class="card">
        <div class="card-head"><h3>Assumptions, with sources</h3><span class="hint" id="assumecount"></span></div>
        <div class="filter" id="afilter"></div>
        <div class="scroll"><table class="tbl" id="assumptions"></table></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>Limitations, stated not hidden</h3></div>
        <div class="limits">
          <div>No phase imbalance and no protection study. The feeder is a three-branch LinDistFlow approximation, not a network model.</div>
          <div>Unannounced outages cannot be forecast. They are handled by a held reserve, not by prediction.</div>
          <div>Second-life battery degradation and round-trip efficiency are simplified to a wear cost and one efficiency figure.</div>
          <div>Load is calibrated to Telangana LT-I consumption and a published Indian residential shape, not metered at a pilot.</div>
          <div>Every reliability number is simulated. A pilot would meter the same four quantities this page reports.</div>
        </div>
      </div>
    </div>
  </section>

  </div>
</main>

<footer>
  <div class="wrap in">
    <div id="footmeta">GridFlex</div>
    <div>static file · no network requests · rebuild with <code>python run.py</code></div>
  </div>
</footer>

<script>
(function(){
"use strict";
var D = __DATA__ || {};
var M = D.scenarios || {}, H = D.headline || {}, CI = D.ci || {};
var MODES = Array.isArray(D.modes) ? D.modes : Object.keys(M);
var DAYS = Array.isArray(D.days) ? D.days : [];
var META = D.meta || {}, ECON = D.econ || {}, EQUITY = D.equity || {};
var SIZING = D.sizing || {}, DISCOM = D.discom || {};
var WHATIF = (D.whatif && D.whatif.results) || [], ASSUME = D.assumptions || [];
var REASONS = D.reasons || {};
var SANS = 'system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif';
var MONO = 'ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,monospace';
var RM = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
var $ = function(s, r){ return (r || document).querySelector(s); };
var $$ = function(s, r){ return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
function esc(s){
  return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];
  });
}
function nf(v, d){
  if (v === null || v === undefined || (typeof v === "number" && isNaN(v))) return "–";
  var q = (d == null ? 1 : d);
  return Number(v).toLocaleString("en-IN", {minimumFractionDigits:q, maximumFractionDigits:q});
}
function int(v){ return nf(v, 0); }
function rgba(hex, a){
  var h = String(hex || "#000").replace("#", "");
  if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
  var n = parseInt(h, 16);
  return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
}
function tokens(){
  var cs = getComputedStyle(document.documentElement);
  var g = function(n){ return cs.getPropertyValue(n).trim(); };
  return {ink:g("--ink"), ink2:g("--ink-2"), muted:g("--muted"), line:g("--line"), line2:g("--line-2"),
    surface:g("--surface"), surface2:g("--surface-2"), green:g("--green"), pine:g("--pine"),
    mint:g("--mint"), amber:g("--amber"), clay:g("--clay"), blue:g("--blue"),
    violet:g("--violet"), slate:g("--slate"),
    dark: !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)};
}
var T = tokens();

/* ---------- data access ---------- */
function mean(mode, key){
  var c = CI[mode] && CI[mode][key];
  if (c && c.mean != null) return c.mean;
  return M[mode] ? M[mode][key] : null;
}
function hmean(key){
  var h = H[key];
  if (h && typeof h === "object" && h.value != null) return h.value;
  if (h != null && typeof h !== "object") return h;
  return mean("mpc_full", key);
}
function seedCount(){
  var c = CI.mpc_full && CI.mpc_full.outage_hours_per_day;
  return c && c.n ? c.n : (H.outage_hours_per_day && H.outage_hours_per_day.seeds) || 0;
}
var hasRun = MODES.length > 0 && Object.keys(M).length > 0;
var SEEDS = seedCount();

/* ---------- charts ---------- */
var charts = {};
function chart(id, cfg){
  var el = document.getElementById(id);
  if (!el) return null;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(el, cfg);
  return charts[id];
}
function chartDefaults(){
  Chart.defaults.font.family = SANS;
  Chart.defaults.font.size = 11.5;
  Chart.defaults.color = T.muted;
  Chart.defaults.borderColor = T.line;
  Chart.defaults.animation = RM ? false : {duration:420, easing:"easeOutCubic"};
  var t = Chart.defaults.plugins.tooltip;
  t.backgroundColor = T.dark ? "#E9EFEA" : "#121A17";
  t.titleColor = T.dark ? "#121A17" : "#FFFFFF";
  t.bodyColor = T.dark ? "rgba(18,26,23,.84)" : "rgba(255,255,255,.9)";
  t.borderWidth = 0; t.cornerRadius = 10; t.padding = 11;
  t.boxWidth = 8; t.boxHeight = 8; t.usePointStyle = true; t.displayColors = true;
  t.titleFont = {family:SANS, size:11, weight:"600"};
  t.bodyFont = {family:MONO, size:11.5};
  var lg = Chart.defaults.plugins.legend.labels;
  lg.color = T.ink2; lg.boxWidth = 8; lg.boxHeight = 8; lg.usePointStyle = true;
  lg.pointStyle = "circle"; lg.padding = 14; lg.font = {family:SANS, size:11.5};
}
function base(extra){
  var o = {responsive:true, maintainAspectRatio:false,
    interaction:{mode:"index", intersect:false},
    layout:{padding:{top:4, right:8, bottom:0, left:0}},
    plugins:{legend:{display:true, position:"bottom", align:"start"}}};
  for (var k in (extra || {})) o[k] = extra[k];
  return o;
}
function axes(o){
  o = o || {};
  var x = {grid:{display:false}, border:{display:false},
    ticks:{maxTicksLimit:o.xticks || 9, padding:6, color:T.muted, font:{family:MONO, size:10}}};
  var y = {grid:{color:T.line, drawTicks:false}, border:{display:false},
    ticks:{padding:8, color:T.muted, font:{family:MONO, size:10}}};
  if (o.fmt) y.ticks.callback = o.fmt;
  if (o.y0 != null) y.min = o.y0;
  if (o.y1 != null) y.max = o.y1;
  if (o.xgrid) x.grid = {color:T.line, drawTicks:false};
  if (o.ygrid === false) y.grid = {display:false};
  if (o.xopts) for (var k in o.xopts) x[k] = o.xopts[k];
  if (o.yopts) for (var j in o.yopts) y[j] = o.yopts[j];
  var scales = {x:x, y:y};
  if (o.y2) scales.y1 = {position:"right", grid:{display:false}, border:{display:false},
    ticks:{padding:8, color:T.muted, font:{family:MONO, size:10}, callback:o.y2fmt}};
  return scales;
}
function series(label, data, color, extra){
  var o = {label:label, data:data, borderColor:color, backgroundColor:rgba(color, .13),
    borderWidth:2, pointRadius:0, pointHoverRadius:4, pointHoverBorderWidth:2,
    pointHoverBackgroundColor:color, tension:.3, fill:false};
  for (var k in (extra || {})) o[k] = extra[k];
  return o;
}
function barLabels(fmt, color){
  return {id:"barLabels", afterDatasetsDraw:function(c){
    var ctx = c.ctx; ctx.save();
    ctx.font = "600 10.5px " + MONO;
    ctx.fillStyle = color || T.ink2;
    c.data.datasets.forEach(function(ds, di){
      var meta = c.getDatasetMeta(di);
      if (meta.hidden) return;
      meta.data.forEach(function(el, i){
        var v = ds.data[i];
        if (v === null || v === undefined || isNaN(v)) return;
        if (c.options.indexAxis === "y"){
          var neg = v < 0;
          ctx.textAlign = neg ? "right" : "left";
          ctx.textBaseline = "middle";
          ctx.fillText(fmt(v), el.x + (neg ? -7 : 7), el.y);
        } else {
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(fmt(v), el.x, el.y - 5);
        }
      });
    });
    ctx.restore();
  }};
}
function scatterLabels(color){
  return {id:"scatterLabels", afterDatasetsDraw:function(c){
    var ctx = c.ctx; ctx.save();
    ctx.font = "600 10px " + MONO; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    c.data.datasets.forEach(function(ds, di){
      if (ds.label === "knee") return;
      var meta = c.getDatasetMeta(di);
      if (meta.hidden) return;
      ctx.fillStyle = color || T.muted;
      meta.data.forEach(function(el, i){
        var raw = ds.data[i] || {};
        if (raw.kwh == null) return;
        ctx.fillText(nf(raw.kwh, 0) + " kWh", el.x + 9, el.y - 8);
      });
    });
    ctx.restore();
  }};
}
function pointLabels(fmt, color, index){
  return {id:"pointLabels", afterDatasetsDraw:function(c){
    var dsI = index || 0, meta = c.getDatasetMeta(dsI);
    var ctx = c.ctx; ctx.save();
    ctx.font = "600 10.5px " + MONO; ctx.fillStyle = color || T.ink2;
    ctx.textAlign = "center"; ctx.textBaseline = "bottom";
    meta.data.forEach(function(p, i){
      var v = c.data.datasets[dsI].data[i];
      if (v == null) return;
      ctx.fillText(fmt(v), p.x, p.y - 9);
    });
    ctx.restore();
  }};
}
function hhmm(i){ return ("0" + Math.floor(i / 4)).slice(-2) + ":" + ("0" + (i % 4) * 15).slice(-2); }
function sum(a){ return (a || []).reduce(function(x, y){ return x + y; }, 0); }

function scMeta(){
  return {
    grid_only:            ["Grid only", T.clay, "no flexibility: the feeder limit binds and demand is cut"],
    pv_batt_naive:        ["PV + battery, unmanaged", T.slate, "the battery chases its own schedule, not the feeder"],
    rule_reserve_tou:     ["Rule + reserve + solar DR", T.amber, "fixed rules, a held reserve and a day-time shift"],
    mpc_no_dr:            ["MPC, no demand response", T.blue, "optimised, but flexible loads are not moved"],
    mpc_persistence:      ["MPC, persistence forecast", T.violet, "the optimiser is fed yesterday's weather"],
    mpc_full:             ["GridFlex", T.green, "forecast + MILP + real-time correction + fair allocation"],
    oracle:               ["Oracle forecast", T.pine, "perfect foresight: the ceiling, not a deployable option"]
  };
}
function scLabel(m){ return (scMeta()[m] || [m.replace(/_/g, " ")])[0]; }

/* ---------- overview ---------- */
var dayReady = false, reasonIdx = -1;
function drawOverview(){
  var g = mean("mpc_full", "outage_hours_per_day");
  var u = mean("pv_batt_naive", "outage_hours_per_day");
  var q = mean("grid_only", "outage_hours_per_day");
  var ci = (CI.mpc_full || {}).outage_hours_per_day;
  var cut = (u && g != null) ? (1 - g / u) * 100 : null;
  var seedTag = SEEDS ? SEEDS + "-seed mean" : "single seed";
  var hh = H.outage_hours_per_day || {};

  var rungs = [
    ["Grid only", q, T.clay, false],
    ["PV + battery, unmanaged", u, T.slate, false],
    ["GridFlex", g, T.green, true]
  ].map(function(r){
    var max = Math.max(q || 0, u || 0, g || 0) || 1;
    return '<div class="rung' + (r[3] ? ' lead' : '') + '">' +
      '<div class="lbl"><i style="background:' + r[2] + '"></i>' + esc(r[0]) + '</div>' +
      '<div class="track"><div class="fill" style="background:' + rgba(r[2], r[3] ? .9 : .5) +
        ';width:' + (r[1] / max * 100) + '%"></div></div>' +
      '<div class="val">' + nf(r[1], 2) + '<span>h/day</span></div></div>';
  }).join("");

  $("#hero").innerHTML = '<div class="hero-grid">' +
    '<div class="hero-main">' +
      '<div class="eyebrow">GridFlex · ' + seedTag + '</div>' +
      '<div class="big">' + nf(g, 2) + '<span class="unit">h/day</span></div>' +
      '<p class="hero-line">critical supply interrupted. The same panels and battery with no control: <b>' +
        nf(u, 2) + '</b>. The bare grid: <b>' + nf(q, 2) + '</b>.</p>' +
      '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:12px">' +
        (cut != null ? '<span class="chip good">▼ ' + nf(cut, 0) + '% vs unmanaged</span>' : '') +
        '<span class="chip">' + (META.test_days || "–") + ' held-out days</span>' +
        '<span class="chip">' + (META.n_hh || "–") + ' homes · ' + (META.pv_kwp || "–") + ' kWp PV · ' +
          (META.bat_kwh || "–") + ' kWh battery</span>' +
      '</div>' +
      '<div class="ci" style="margin-top:18px">' +
        (ci && ci.lo != null
          ? '95% CI ' + nf(ci.lo, 2) + ' – ' + nf(ci.hi, 2) + ' over ' + ci.n + ' independent load/outage seeds' +
            (hh.single_seed != null ? ' · single-seed replay ' + nf(hh.single_seed, 2) : '')
          : 'Single seed. Rerun with <code>--seeds 20</code> for confidence intervals.') +
      '</div>' +
    '</div>' +
    '<div class="hero-side">' +
      '<div class="hint" style="margin-bottom:12px">Same transformer and weather; only the control software changes.</div>' +
      '<div class="ladder">' + rungs + '</div>' +
    '</div>' +
  '</div>';

  $("#glance").innerHTML = [
    stat("evening_availability_pct", "Evening availability, 18–23 h", "%", 1, false),
    stat("critical_served_pct", "Critical energy served", "%", 1, false),
    stat("unserved_critical_kwh_per_day", "Critical energy unserved", " kWh/day", 1, true),
    stat("evening_peak_import_kw", "Evening peak import", " kW", 1, true),
    stat("bill_inr_per_hh_month", "Grid bill per household", " ₹/month", 0, true),
    stat("self_consumption_pct", "Solar self-consumed", "%", 1, false)
  ].join("");

  if (!dayReady) buildDaySelector();
  renderDay();
}

function stat(key, label, unit, digits, lowerBetter){
  var a = hmean(key), b = mean("pv_batt_naive", key);
  var d = "", cls = "good";
  if (a != null && b != null) {
    if (unit === "%") {
      var pp = a - b;
      d = (pp >= 0 ? "+" : "−") + nf(Math.abs(pp), 1) + " pp vs unmanaged";
    } else if (unit.indexOf("₹") === 0) {
      var diff = a - b;
      d = (diff >= 0 ? "+" : "−") + "₹" + int(Math.abs(diff)) + " vs unmanaged";
    } else {
      var rel = (a - b) / (Math.abs(b) || 1) * 100;
      d = (rel >= 0 ? "+" : "−") + nf(Math.abs(rel), 0) + "% vs unmanaged";
    }
    var better = lowerBetter ? a < b : a > b;
    cls = better ? "good" : "bad";
  }
  return '<div class="stat"><b>' + nf(a, digits) + esc(unit) + '</b><span>' + esc(label) +
         '</span><em class="' + cls + '">' + esc(d) + '</em></div>';
}

function buildDaySelector(){
  var sel = $("#daysel");
  if (!sel || !DAYS.length) return;
  sel.innerHTML = DAYS.map(function(d, i){
    return '<option value="' + i + '">' + esc(d.label) + '</option>';
  }).join("");
  REASONS.day = REASONS.day || "";
  reasonIdx = -1;
  if (REASONS.day) {
    for (var i = 0; i < DAYS.length; i++) {
      if (DAYS[i].label.slice(0, 6) === REASONS.day.slice(0, 6)) { reasonIdx = i; break; }
    }
  }
  sel.value = String(reasonIdx >= 0 ? reasonIdx : 0);
  sel.onchange = renderDay;
  dayReady = true;
}

function renderDay(){
  var sel = $("#daysel");
  if (!sel || !DAYS.length) return;
  var i = Math.max(0, Math.min(DAYS.length - 1, +sel.value || 0));
  var d = DAYS[i];
  var tag = (d.label.split("·")[1] || "").trim();
  var tagCls = /outage/i.test(tag) ? "bad" : (/stress/i.test(tag) ? "warn" : "");
  var pvKwh = sum(d.pv) * .25, shedKwh = sum(d.shed.mpc_full) * .25;
  var peak = Math.max.apply(null, d.g.mpc_full);

  $("#daymeta").innerHTML =
    '<span class="chip ' + tagCls + '">' + esc(tag || "normal") + '</span>' +
    '<div class="facts-mini">' +
      '<div><b>' + nf(pvKwh, 0) + ' kWh</b>solar generated</div>' +
      '<div><b>' + nf(shedKwh, 1) + ' kWh</b>critical unserved · GridFlex</div>' +
      '<div><b>' + nf(peak, 1) + ' kW</b>peak import</div>' +
    '</div>';

  $("#ribbon").innerHTML = d.cap.map(function(c, k){
    var cls = c === 0 ? "island" : (c <= 25 ? "stress" : (c <= 50 ? "evening" : "normal"));
    var what = c === 0 ? "feeder off (outage)" :
      (c <= 25 ? "DISCOM stress limit " + nf(c, 0) + " kW" :
      (c <= 50 ? "evening allocation " + nf(c, 0) + " kW" : "normal limit " + nf(c, 0) + " kW"));
    return '<i class="' + cls + '" title="' + hhmm(k) + ' · ' + what + '"></i>';
  }).join("");

  var X = d.load.map(function(_, k){ return hhmm(k); });
  chart("day1", {
    type:"line",
    data:{labels:X, datasets:[
      series("Load", d.load, T.slate, {borderWidth:1.4}),
      series("Solar", d.pv, T.amber, {fill:true, backgroundColor:rgba(T.amber, .16)}),
      series("Grid import · GridFlex", d.g.mpc_full, T.green, {borderWidth:2.2}),
      series("Grid import · unmanaged", d.g.pv_batt_naive, T.slate, {borderDash:[4,3], borderWidth:1.5}),
      series("Feeder limit", d.cap, T.clay, {borderDash:[6,4], stepped:true, borderWidth:1.4, fill:false})
    ]},
    options: base({
      plugins:{legend:{display:true, position:"bottom", align:"start"}, tooltip:{callbacks:{label:function(c){
        return " " + c.dataset.label + ": " + nf(c.parsed.y, 1) + " kW";
      }}}},
      scales: axes({fmt:function(v){ return nf(v, 0); }})
    })
  });

  chart("day2", {
    type:"line",
    data:{labels:X, datasets:[
      series("Battery SOC · GridFlex", d.soc.mpc_full, T.green, {fill:true, backgroundColor:rgba(T.green, .12)}),
      series("Battery SOC · unmanaged", d.soc.pv_batt_naive, T.slate, {borderDash:[4,3], borderWidth:1.5, fill:false}),
      series("Unserved · GridFlex", d.shed.mpc_full, T.clay, {fill:true, backgroundColor:rgba(T.clay, .3), borderWidth:0}),
      series("Unserved · unmanaged", d.shed.pv_batt_naive, T.violet, {fill:true, backgroundColor:rgba(T.violet, .16), borderWidth:0})
    ]},
    options: base({
      plugins:{legend:{display:true, position:"bottom", align:"start"}, tooltip:{callbacks:{label:function(c){
        return " " + c.dataset.label + ": " + nf(c.parsed.y, 1) + " " + (c.datasetIndex < 2 ? "kWh SOC" : "kWh unserved");
      }}}},
      scales: axes({fmt:function(v){ return nf(v, 0); }})
    })
  });

  var S = REASONS.summary || {};
  var FACT = [
    ["pv_kwh", "Solar generated", "kWh", 0],
    ["load_kwh", "Total load", "kWh", 0],
    ["grid_kwh", "Grid import", "kWh", 0],
    ["export_kwh", "Exported", "kWh", 0],
    ["critical_served_kwh", "Critical energy served", "kWh", 0],
    ["unserved_kwh", "Critical energy unserved", "kWh", 1],
    ["max_import_kw", "Peak import", "kW", 1],
    ["min_soc_kwh", "Lowest battery SOC", "kWh", 0],
    ["evening_available_pct", "Evening availability", "%", 0]
  ];
  $("#summary").innerHTML = FACT.filter(function(f){ return S[f[0]] != null; }).map(function(f){
    return '<div><span>' + f[1] + '</span><b>' + nf(S[f[0]], f[3]) + ' ' + f[2] + '</b></div>';
  }).join("") || '<div class="hint">No daily summary in this payload.</div>';

  var same = REASONS.day && d.label.slice(0, 6) === REASONS.day.slice(0, 6);
  $("#reasonday").textContent = REASONS.day ? "· " + REASONS.day : "";
  $("#reasonhint").innerHTML = same ? "Hourly excerpt of the controller's quarter-hour trace." :
    'Trace built for ' + esc(REASONS.day || "another day") + '. <button type="button" class="linkbtn" id="jumpday">View that day</button>';
  $("#reasons").innerHTML = (REASONS.hourly || []).filter(function(_, k){ return k % 4 === 0; })
    .slice(0, 18).map(function(x){
      return '<li class="' + (x.shed > 0 ? "alert" : "") + '"><span class="t">' + esc(x.time) +
             '</span><span>' + esc(x.text) + '</span></li>';
    }).join("") || '<li><span class="t">–</span><span>No trace in this payload.</span></li>';
  var jump = $("#jumpday");
  if (jump) jump.onclick = function(){ sel.value = String(reasonIdx); renderDay(); };
}

/* ---------- scenarios ---------- */
function drawScenarios(){
  var sc = scMeta();
  var met = function(m, k){ return mean(m, k); };
  var order = MODES.slice().sort(function(a, b){ return met(a, "outage_hours_per_day") - met(b, "outage_hours_per_day"); });
  var labels = order.map(scLabel);
  var basis = SEEDS ? SEEDS + "-seed mean" : "single-seed replay";

  chart("ablation", {
    type:"bar",
    data:{labels:labels, datasets:[{data:order.map(function(m){ return met(m, "outage_hours_per_day"); }),
      backgroundColor:order.map(function(m){ return sc[m][1]; }), borderRadius:4, borderSkipped:false,
      maxBarThickness:24}]},
    options: base({indexAxis:"y", plugins:{legend:{display:false}, tooltip:{callbacks:{label:function(c){
      return " " + nf(c.parsed.x, 2) + " interrupted h/day";
    }}}}, scales:axes({maxTicks:1, fmt:function(v){ return nf(v, 1); },
      x:{grid:{color:T.line, drawTicks:false}}, y:{grid:{display:false}, ticks:{color:T.ink2, padding:8}}})}),
    plugins:[barLabels(function(v){ return nf(v, 2); })]
  });

  if ($("#ablatenote")) {
    var diff = Math.abs(met("mpc_full", "outage_hours_per_day") - met("mpc_persistence", "outage_hours_per_day"));
    var drop = met("mpc_no_dr", "outage_hours_per_day") - met("mpc_full", "outage_hours_per_day");
    $("#ablatenote").innerHTML = (SEEDS ? SEEDS + "-seed mean. " : "") + "GridFlex and the persistence-forecast variant sit " + nf(diff, 2) +
      " h/day apart on this window: the learned forecast is not what earns the gain here, the optimiser and demand response are (" +
      nf(drop, 2) + " h/day between MPC with and without flexible loads). The docs report this rather than hiding it.";
  }

  var rows = [
    ["outage_hours_per_day", "Interrupted h/day", 2],
    ["evening_availability_pct", "Evening availability %", 1],
    ["unserved_critical_kwh_per_day", "Unserved kWh/day", 1],
    ["flex_served_pct", "Flex served %", 1],
    ["bill_inr_per_hh_month", "Bill ₹/hh·month", 0],
    ["curtailment_pct", "Curtailed %", 1]
  ];
  $("#abtable").innerHTML =
    '<caption>' + basis + ' · identical weather, load and outage draws</caption>' +
    '<thead><tr><th>scenario</th>' + rows.map(function(r){ return '<th>' + r[1] + '</th>'; }).join("") + '</tr></thead><tbody>' +
    MODES.map(function(m){
      return '<tr class="' + (m === "mpc_full" ? "me" : "") + '"><td><span class="dot" style="background:' +
        sc[m][1] + '"></span>' + esc(sc[m][0]) + '</td>' +
        rows.map(function(r){ return '<td class="n">' + nf(met(m, r[0]), r[2]) + '</td>'; }).join("") + '</tr>';
    }).join("") + '</tbody>';

  chart("billbars", {
    type:"bar",
    data:{labels:MODES.map(scLabel), datasets:[{data:MODES.map(function(m){ return met(m, "bill_inr_per_hh_month"); }),
      backgroundColor:MODES.map(function(m){ return rgba(sc[m][1], .82); }), borderRadius:4,
      borderSkipped:false, maxBarThickness:44}]},
    options: base({
      plugins:{legend:{display:false}, tooltip:{callbacks:{label:function(c){
        return " ₹" + int(c.parsed.y) + " per household per month";
      }}}},
      scales:axes({
        fmt:function(v){ return "₹" + int(v); },
        xopts:{ticks:{maxTicksLimit:7, color:T.muted, font:{family:SANS, size:10}}}
      })
    }),
    plugins:[barLabels(function(v){ return "₹" + int(v); })]
  });

  var modes = Object.keys(CI);
  $("#cibadge").innerHTML = modes.length
    ? '<span class="chip good">' + (CI[modes[0]].outage_hours_per_day.n || "–") + ' seeds</span>'
    : '<span class="chip">not run</span>';
  $("#cinote").textContent = modes.length
    ? "Mean and 95% confidence interval over " + (CI[modes[0]].outage_hours_per_day.n || "–") +
      " independent load and outage draws on the same real weather. These intervals are what the headline quotes."
    : "Run with --seeds 20 to populate confidence intervals.";

  if (!modes.length) {
    $("#cirange").innerHTML = '<div class="empty-inline">No confidence intervals in this payload — the run used a single seed. The scenario table above is the whole evidence.</div>';
    $("#citable").innerHTML = "";
    return;
  }

  var key = "outage_hours_per_day";
  var all = modes.map(function(m){ return CI[m][key]; }).filter(Boolean);
  var lo = Math.min.apply(null, all.map(function(c){ return c.lo; }));
  var hi = Math.max.apply(null, all.map(function(c){ return c.hi; }));
  var span = (hi - lo) || 1;
  $("#cirange").innerHTML = modes.filter(function(m){ return CI[m][key]; }).map(function(m){
    var c = CI[m][key], sc2 = sc[m] || ["", T.slate];
    var left = (c.lo - lo) / span * 100, width = (c.hi - c.lo) / span * 100, mid = (c.mean - lo) / span * 100;
    return '<div class="row"><div class="name"><span class="dot" style="background:' + sc2[1] + '"></span>' +
      esc(sc2[0]) + '</div>' +
      '<div class="track"><div class="band" style="left:' + left + '%;width:' + width + '%;background:' +
      rgba(sc2[1], .55) + '"></div><div class="mean" style="left:' + mid + '%"></div></div>' +
      '<div class="num">' + nf(c.mean, 2) + ' [' + nf(c.lo, 2) + ', ' + nf(c.hi, 2) + ']</div></div>';
  }).join("");

  var cols = [["evening_availability_pct", "Evening availability %", 1],
              ["unserved_critical_kwh_per_day", "Unserved kWh/day", 1],
              ["bill_inr_per_hh_month", "Bill ₹/hh·month", 0]];
  $("#citable").innerHTML = '<thead><tr><th>scenario</th>' +
    cols.map(function(c){ return '<th>' + c[1] + '</th>'; }).join("") + '</tr></thead><tbody>' +
    modes.map(function(m){
      return '<tr class="' + (m === "mpc_full" ? "me" : "") + '"><td>' +
        '<span class="dot" style="background:' + (sc[m] || ["", T.slate])[1] + '"></span>' + esc(scLabel(m)) + '</td>' +
        cols.map(function(c){
          var x = CI[m][c[0]];
          return '<td class="n">' + (x ? nf(x.mean, c[2]) + ' <span class="hint">[' + nf(x.lo, c[2]) + ', ' + nf(x.hi, c[2]) + ']</span>' : '–') + '</td>';
        }).join("") + '</tr>';
    }).join("") + '</tbody>';
}

/* ---------- DISCOM ---------- */
function drawDiscom(){
  var K = DISCOM, day = DAYS[Math.max(0, Math.min(DAYS.length - 1, +($("#daysel") ? $("#daysel").value : 0) || 0))] || null;
  if ($("#discomday")) $("#discomday").textContent = K.day || "";

  $("#discomkpis").innerHTML = [
    kpi(nf(K.peak_import_kw, 0) + " kW", "peak transformer import"),
    kpi(nf(K.transformer_loading_pct, 0) + "%", "of transformer rating"),
    kpi(nf(K.saidi_minutes_per_day, 0) + " min", "SAIDI-like interruption per day"),
    kpi(nf(K.voltage_min_pu, 3) + " pu", "lowest end-of-feeder voltage"),
    kpi(nf(K.loss_pct, 2) + "%", "technical-loss proxy"),
    kpi(nf(K.participating_homes, 0), "homes providing flexibility")
  ].join("");

  var probs = (K.risk && K.risk.outage_probability_by_hour) || [];
  $("#heat").innerHTML = probs.map(function(p, h){
    var a = .08 + .78 * Math.min(1, p);
    var light = p > .46;
    return '<div class="cell" style="background:' + rgba(T.clay, a) + ';border-color:' + rgba(T.clay, a + .12) + '" ' +
      'title="' + ("0" + h).slice(-2) + ':00 · ' + nf(p * 100, 0) + '% chance of an outage or announced stress window">' +
      '<span class="h" style="color:' + (light ? "rgba(255,255,255,.8)" : T.muted) + '">' + ("0" + h).slice(-2) + '</span>' +
      '<span class="p" style="color:' + (light ? "#fff" : T.ink) + '">' + nf(p * 100, 0) + '%</span></div>';
  }).join("") || '<div class="empty-inline">No hourly risk array in this payload.</div>';

  var R = K.risk || {};
  var X = (R.prob || []).map(function(_, i){ return hhmm(i); });
  chart("risk", {
    type:"line",
    data:{labels:X, datasets:[
      series("Expected shortfall", R.expected_shortfall_kw || [], T.amber, {fill:true, backgroundColor:rgba(T.amber, .18)}),
      series("Net load", R.net_load_kw || [], T.green),
      series("Import cap", R.cap_kw || [], T.clay, {borderDash:[6,4], stepped:true, borderWidth:1.4})
    ]},
    options: base({plugins:{legend:{display:true, position:"bottom", align:"start"}, tooltip:{callbacks:{label:function(c){
      return " " + c.dataset.label + ": " + nf(c.parsed.y, 1) + " kW";
    }}}}, scales:axes({fmt:function(v){ return nf(v, 0); }})})
  });

  if (day) {
    var V = day.v || [];
    var cols = [T.green, T.blue, T.amber];
    chart("volt", {
      type:"line",
      data:{labels:(V[0] || []).map(function(_, i){ return hhmm(i); }),
        datasets: V.map(function(v, b){ return series("branch " + (b + 1), v, cols[b % 3], {borderWidth:1.8}); })},
      options: base({plugins:{legend:{display:true, position:"bottom", align:"start"}, tooltip:{callbacks:{label:function(c){
        return " branch " + (c.datasetIndex + 1) + ": " + nf(c.parsed.y, 3) + " pu";
      }}}}, scales:axes({fmt:function(v){ return nf(v, 2); },
        yopts:{suggestedMin:.93, suggestedMax:1.01}})})
    });
    if ($("#voltnote")) $("#voltnote").textContent = "selected day · limit is 0.94 pu in the model";
  }

  var acts = K.dr_actions || [];
  var maxc = Math.max.apply(null, acts.map(function(a){ return a.credit_inr; }).concat([1]));
  $("#actions").innerHTML = acts.length ? acts.map(function(a){
    return '<div class="action"><div class="rank">' + a.rank + '</div>' +
      '<div><div class="title">' + esc(a.action) + '</div>' +
      '<div class="detail">' + esc(a.detail) + '</div>' +
      '<div class="meter"><i style="width:' + (a.credit_inr / maxc * 100) + '%"></i></div>' +
      '<div class="basis">' + esc(a.basis) + '</div></div>' +
      '<div class="credit">₹' + int(a.credit_inr) + '<span>' + nf(a.kw, 1) + ' kW · ' + nf(a.kwh, 1) + ' kWh / day</span></div></div>';
  }).join("") : '<div class="empty-inline">No dispatchable flexibility on this day. That is itself a result: the feeder had nothing left to offer.</div>';

  var rows = [
    ["Evening peak import", nf(K.evening_peak_import_kw, 1) + " kW"],
    ["Peak transformer loading", nf(K.transformer_loading_pct, 0) + " %"],
    ["Loss proxy", nf(K.loss_pct, 2) + " % of delivered"],
    ["Lost energy per day", nf(K.loss_kwh_per_day, 1) + " kWh"],
    ["Critical served", nf(K.critical_served_pct, 1) + " %"],
    ["Evening availability", nf(K.evening_availability_pct, 1) + " %"],
    ["Voltage violations", nf(K.voltage_violations, 0) + " steps"]
  ];
  $("#discomtable").innerHTML = '<thead><tr><th>indicator</th><th>value</th></tr></thead><tbody>' +
    rows.map(function(r){ return '<tr><td>' + r[0] + '</td><td class="n">' + r[1] + '</td></tr>'; }).join("") + '</tbody>';
}
function kpi(v, l){
  return '<div class="card" style="padding:14px 16px"><b style="display:block;font:600 1.5rem/1.15 ' + MONO +
    ';letter-spacing:-.02em;color:var(--ink)">' + v + '</b><span style="font-size:.72rem;color:var(--muted)">' + l + '</span></div>';
}

/* ---------- equity ---------- */
function drawEquity(){
  var A = EQUITY.archetypes || {}, names = Object.keys(A);
  var LABEL = {low_income:"Low-income", lower_middle:"Lower-middle", middle:"Middle"};
  var maxServed = Math.max.apply(null, names.map(function(n){ return A[n].served_kwh_per_hh_day; }).concat([1]));

  $("#archcards").innerHTML = names.map(function(n){
    var a = A[n];
    var share = META.n_hh ? a.households / META.n_hh * 100 : null;
    return '<div class="card arch"><h4>' + esc(LABEL[n] || n.replace(/_/g, " ")) + '</h4>' +
      '<div class="hh">' + a.households + '</div>' +
      '<div class="hs">households' + (share != null ? ' · ' + nf(share, 0) + '% of the feeder' : '') + '</div>' +
      meter("Critical served", a.critical_served_pct, "%", 1, 100) +
      meter("Evening availability", a.evening_availability_pct, "%", 1, 100) +
      meter("Energy served per household", a.served_kwh_per_hh_day, " kWh/day", 2, maxServed) +
      '</div>';
  }).join("");

  var F = EQUITY.fairness || {};
  $("#jain").innerHTML = nf(F.jain_index, 3) + '<span>Jain index</span>';
  $("#jainnote").textContent = (F.metric || "Jain index on served critical demand") +
    '. Gap between low-income and the average household: ' + nf(F.low_income_gap_pp, 2) + ' pp. Rule: ' + (F.rule || "equal per household") + '.';

  chart("equitychart", {
    type:"bar",
    data:{labels:names.map(function(n){ return LABEL[n] || n; }),
      datasets:[{data:names.map(function(n){ return A[n].unserved_critical_kwh_per_day; }),
        backgroundColor:names.map(function(){ return rgba(T.clay, .78); }),
        borderRadius:4, borderSkipped:false, maxBarThickness:52}]},
    options: base({plugins:{legend:{display:false}, tooltip:{callbacks:{label:function(c){
      return " " + nf(c.parsed.y, 1) + " kWh/day unserved";
    }}}}, scales:axes({fmt:function(v){ return nf(v, 1); }})}),
    plugins:[barLabels(function(v){ return nf(v, 1); })]
  });

  var RU = EQUITY.rules || {};
  if (RU.equal && RU.proportional) {
    var e = RU.equal, p = RU.proportional;
    $("#rulesens").innerHTML =
      '<div class="fact-list">' +
        '<div><span>Jain index</span><b>' + nf(p.fairness.jain_index, 3) + ' <span class="hint">vs ' + nf(e.fairness.jain_index, 3) + '</span></b></div>' +
        '<div><span>Low-income critical served</span><b>' + nf(p.archetypes.low_income.critical_served_pct, 1) + '% <span class="hint">vs ' + nf(e.archetypes.low_income.critical_served_pct, 1) + '%</span></b></div>' +
        '<div><span>Low-income gap to the feeder average</span><b>' + nf(p.fairness.low_income_gap_pp, 2) + ' pp <span class="hint">vs ' + nf(e.fairness.low_income_gap_pp, 2) + ' pp</span></b></div>' +
      '</div>' +
      '<p class="hint" style="margin-top:12px">Both rules were run on the same draws. The controller ships the equal rule because it does not depend on every household\'s demand being measured correctly.</p>';
  } else {
    $("#rulesens").innerHTML = '<div class="empty-inline">Rule sensitivity was not run in this payload.</div>';
  }

  $("#equitytable").innerHTML =
    '<thead><tr><th>archetype</th><th>homes</th><th>h/day</th><th>evening %</th><th>critical %</th><th>kWh/hh·day</th><th>unserved kWh/day</th><th>PV self-used %</th></tr></thead><tbody>' +
    names.map(function(n){
      var a = A[n];
      return '<tr><td>' + esc(LABEL[n] || n) + '</td><td class="n">' + a.households + '</td>' +
        '<td class="n">' + nf(a.outage_hours_per_day, 2) + '</td><td class="n">' + nf(a.evening_availability_pct, 1) + '</td>' +
        '<td class="n">' + nf(a.critical_served_pct, 1) + '</td><td class="n">' + nf(a.served_kwh_per_hh_day, 2) + '</td>' +
        '<td class="n">' + nf(a.unserved_critical_kwh_per_day, 1) + '</td><td class="n">' + nf(a.self_consumption_pct, 1) + '</td></tr>';
    }).join("") + '</tbody>';
}
function meter(label, v, unit, digits, max){
  var pctv = Math.max(0, Math.min(100, (v / (max || 100)) * 100));
  return '<div class="m"><div class="top"><span>' + esc(label) + '</span><b>' + nf(v, digits) + esc(unit) + '</b></div>' +
    '<div class="meter"><i style="width:' + pctv + '%"></i></div></div>';
}

/* ---------- economics ---------- */
function drawEconomics(){
  var E = ECON;
  $("#econkpis").innerHTML = [
    kpi('₹' + int(E.capex_per_hh_inr), "upfront capex per household"),
    kpi('₹' + int(E.annualised_cost_per_hh_month_inr), "annualised cost per household/month"),
    kpi('₹' + int(E.net_value_per_hh_month_inr), "net value per household/month"),
    kpi('₹' + nf(E.cost_per_kwh_critical_delivered_inr, 2), "per kWh of critical energy delivered"),
    kpi(nf(E.payback_years, 1) + " yr", "payback from reliability and DISCOM value"),
    kpi('₹' + int(E.breakeven_fee_per_hh_month_inr), "break-even fee after all value")
  ].join("");

  var billDelta = -Math.abs(E.bill_saving_vs_pv_battery_per_hh_month_inr || 0);
  $("#ledger").innerHTML =
    '<div class="led"><h4>What it costs</h4>' +
      row("Annualised asset cost", "−₹" + int(E.annualised_cost_per_hh_month_inr), "neg") +
      row("Higher grid bill than no control", "−₹" + int(Math.abs(E.bill_saving_vs_pv_battery_per_hh_month_inr)), "neg") +
      '<p class="hint" style="margin:8px 0 0">One-off upfront capex is ₹' + int(E.capex_per_hh_inr) +
        ' per household, already inside the annualised line.</p>' +
    '</div>' +
    '<div class="led"><h4>What it returns</h4>' +
      row("Avoided outage cost, " + nf(E.avoided_unserved_kwh_per_hh_month, 1) + " kWh/hh·month", "+₹" + int(E.outage_value_per_hh_month_inr), "pos") +
      row("DISCOM peak-reduction credit", "+₹" + int(E.discom_peak_credit_per_hh_month_inr), "pos") +
      row("Critical energy delivered", nf(E.critical_kwh_delivered_per_hh_month, 0) + " kWh/hh·month", "") +
    '</div>';

  var r = E.net_value_range_inr || [0, 0];
  var lo = Math.min(r[0], 0), hi = Math.max(r[1], 0), span = (hi - lo) || 1;
  $("#netrange").innerHTML =
    '<div class="rng" style="left:' + ((r[0] - lo) / span * 100) + '%;width:' + ((r[1] - r[0]) / span * 100) + '%"></div>' +
    '<div class="zero" style="left:' + ((0 - lo) / span * 100) + '%"></div>' +
    '<div class="pin" style="left:' + ((E.net_value_per_hh_month_inr - lo) / span * 100) + '%"></div>';
  $("#netrangelabels").innerHTML = '<span>−₹' + int(Math.abs(Math.min(r[0], 0))) + ' · VoLL at the low end</span>' +
    '<span>₹' + int(Math.max(r[1], 0)) + ' · high end</span>';
  var net = document.createElement("div");
  net.className = "netrow";
  net.innerHTML = '<div><div class="lbl">Net value per household per month</div>' +
    '<div class="hint">' + esc(E.counterfactual || "") + '</div></div>' +
    '<b>₹' + int(E.net_value_per_hh_month_inr) + '</b>';
  var host = $("#ledger").parentNode;
  if (!host.querySelector(".netrow")) host.insertBefore(net, $("#netrange"));
  else host.querySelector(".netrow").innerHTML = net.innerHTML;

  var pts = SIZING.points || [], key = SIZING.cost_axis || "net_cost_low_income_per_hh_month_inr";
  var knee = SIZING.knee;
  var ds = function(scheme){
    var c = scheme === "lifeline" ? T.green : T.amber;
    return {label:scheme + " tariff", data:pts.filter(function(p){ return p.fee_scheme === scheme; })
        .map(function(p){ return {x:p.outage_hours_per_day, y:p[key], kwh:p.bat_kwh}; }),
      backgroundColor:c, borderColor:c, pointRadius:5, pointHoverRadius:7, pointStyle:"circle"};
  };
  var pOpts = base({
    plugins:{legend:{display:true, position:"bottom", align:"start"},
      tooltip:{callbacks:{label:function(c){
        var p = c.raw || {};
        return " " + (p.kwh ? p.kwh + " kWh · " : "") + nf(p.x, 2) + " h/day · ₹" + int(p.y) + "/hh·month";
      }}}},
    scales:{
      x:{grid:{display:false}, border:{display:false},
        title:{display:true, text:"interrupted critical hours per day", color:T.muted, font:{size:10.5}},
        ticks:{color:T.muted, font:{family:MONO, size:10}}},
      y:{grid:{color:T.line, drawTicks:false}, border:{display:false},
        title:{display:true, text:"net cost, low-income ₹/hh·month", color:T.muted, font:{size:10.5}},
        ticks:{color:T.muted, font:{family:MONO, size:10}, callback:function(v){ return "₹" + int(v); }}}
    }
  });
  chart("pareto", {type:"scatter", data:{datasets:[ds("lifeline"), ds("flat"),
    {label:"knee", data:knee ? [{x:knee.outage_hours_per_day, y:knee[key]}] : [],
     backgroundColor:"transparent", borderColor:T.clay, borderWidth:2, pointRadius:9, pointStyle:"circle"}]},
    options:pOpts, plugins:[scatterLabels(T.muted)]});

  if ($("#kneenote")) $("#kneenote").textContent = knee ? "frontier knee at " + knee.bat_kwh + " kWh on the cost axis" : "";
  var lifeline = pts.filter(function(p){ return p.fee_scheme === "lifeline"; })
    .sort(function(a, b){ return a.bat_kwh - b.bat_kwh; });
  if (lifeline.length >= 2 && knee) {
    var atKnee = lifeline.filter(function(p){ return p.bat_kwh === knee.bat_kwh; })[0] || lifeline[0];
    var smaller = lifeline.filter(function(p){ return p.bat_kwh < atKnee.bat_kwh; }).pop();
    var bigger = lifeline.filter(function(p){ return p.bat_kwh > atKnee.bat_kwh; })[0];
    var parts = [];
    if (smaller) parts.push("Going from " + smaller.bat_kwh + " to " + atKnee.bat_kwh + " kWh buys " +
      nf(smaller.outage_hours_per_day - atKnee.outage_hours_per_day, 2) + " h/day for ₹" +
      int(atKnee.cost_per_hh_month_inr - smaller.cost_per_hh_month_inr) + "/hh·month.");
    if (bigger) parts.push("The next step to " + bigger.bat_kwh + " kWh buys " +
      nf(atKnee.outage_hours_per_day - bigger.outage_hours_per_day, 2) + " h/day for ₹" +
      int(bigger.cost_per_hh_month_inr - atKnee.cost_per_hh_month_inr) + " more.");
    if (smaller && bigger && (smaller.outage_hours_per_day - bigger.outage_hours_per_day) < 0.12) {
      parts.push("Reliability flattens well before the cost curve does: the knee at " + atKnee.bat_kwh +
        " kWh is where net cost is lowest, not where each extra kWh stops mattering.");
    }
    $("#kneefacts").innerHTML = '<div style="border:0;padding:0;display:block;color:var(--muted);font-size:.78rem;line-height:1.6">' +
      parts.join(" ") + '</div>';
  }

  var F = E.fee_tiers || {};
  $("#tiers").innerHTML = [
    ["Lifeline", F.lifeline_low_income_inr, "low-income households, 55% of critical load", true],
    ["Standard", F.standard_inr, "most households", false],
    ["Higher use", F.higher_use_inr, "larger homes and EV owners", false]
  ].map(function(t){
    return '<div class="tier ' + (t[3] ? "free" : "") + '"><span>' + t[0] + '</span><b>₹' + int(t[1]) +
      '</b><span>' + t[2] + '</span></div>';
  }).join("");
  if ($("#tiernote")) $("#tiernote").innerHTML = "Weighted collection ₹" + int(F.collected_per_hh_month_inr) +
    "/hh·month recovers " + nf(F.gross_cost_recovery_pct, 0) + "% of gross cost and " +
    nf(F.net_cost_recovery_pct, 0) + "% once reliability and DISCOM value are counted. " + esc(E.lifeline_note || "");

  var rows = [
    ["Upfront capex per household", "₹" + int(E.capex_per_hh_inr)],
    ["Battery capex assumption", "₹" + int(E.battery_capex_per_kwh_inr) + " / kWh"],
    ["Annualised cost", "₹" + int(E.annualised_cost_per_hh_month_inr) + " / hh·month"],
    ["Bill change vs uncontrolled PV+battery", (E.bill_saving_vs_pv_battery_per_hh_month_inr >= 0 ? "+" : "−") +
      "₹" + int(Math.abs(E.bill_saving_vs_pv_battery_per_hh_month_inr)) + " / hh·month"],
    ["Avoided unserved energy", nf(E.avoided_unserved_kwh_per_hh_month, 1) + " kWh / hh·month"],
    ["Evening peak reduction", nf(E.evening_peak_reduction_kw, 1) + " kW"],
    ["Critical energy delivered", nf(E.critical_kwh_delivered_per_hh_month, 1) + " kWh / hh·month"],
    ["Cost per kWh of unserved energy avoided", "₹" + nf(E.cost_per_kwh_unserved_avoided_inr, 2)],
    ["Payback period", nf(E.payback_years, 1) + " years"],
    ["Break-even fee after all value", "₹" + int(E.breakeven_fee_per_hh_month_inr) + " / hh·month"]
  ];
  $("#econtable").innerHTML = '<thead><tr><th>item</th><th>value</th></tr></thead><tbody>' +
    rows.map(function(r){ return '<tr><td>' + r[0] + '</td><td class="n">' + r[1] + '</td></tr>'; }).join("") + '</tbody>';
}
function row(label, value, cls){
  return '<div class="row"><span>' + esc(label) + '</span><b class="' + cls + '">' + esc(value) + '</b></div>';
}

/* ---------- what-if ---------- */
var W = null, WVAL = {};
function drawWhatIf(){
  if (!WHATIF.length) {
    $("#whatifbody").innerHTML = '<div class="empty-inline">The what-if grid is only built in a full run. Open a payload produced without <code>--quick</code>.</div>';
    $("#whtkpis").innerHTML = "";
    return;
  }
  if (!W) {
    var bats = uniq("bat_kwh"), pvs = uniq("pv_scale"), evs = uniq("ev_scale"), oms = uniq("outage_mult");
    W = {bat:nearest(bats, META.bat_kwh || 100), pv:1.0, ev:1.0, om:1.0};
    $("#whatiffixed").textContent = pvs.length + " solar × " + evs.length + " EV × " + oms.length +
      " outage levels for each of " + bats.length + " battery sizes — " + WHATIF.length +
      " simulated cases, nothing interpolated";
    buildSeg("#seg-bat", bats, function(v){ return int(v) + " kWh"; }, "bat", W, drawWhatIf);
    buildSeg("#seg-om", oms, function(v){ return "×" + nf(v, 2); }, "om", W, drawWhatIf);
    buildSeg("#seg-pv", pvs, function(v){ return nf(v * 100, 0) + "% PV"; }, "pv", W, drawWhatIf);
    buildSeg("#seg-ev", evs, function(v){ return "×" + nf(v, 1) + " EV"; }, "ev", W, drawWhatIf);

  }
  var row = WHATIF.filter(function(p){
    return p.bat_kwh === W.bat && Math.abs(p.pv_scale - W.pv) < 1e-9 &&
           Math.abs(p.ev_scale - W.ev) < 1e-9 && Math.abs(p.outage_mult - W.om) < 1e-9;
  })[0];
  if (!row) {
    $("#whtkpis").innerHTML = '<div class="empty-inline">This combination was not simulated. Pick another.</div>';
    return;
  }
  var ref = WHATIF.filter(function(p){
    return p.bat_kwh === W.bat && Math.abs(p.pv_scale - 1) < 1e-9 &&
           Math.abs(p.ev_scale - 1) < 1e-9 && Math.abs(p.outage_mult - 1) < 1e-9;
  })[0];
  var dh = ref ? row.outage_hours_per_day - ref.outage_hours_per_day : null;
  $("#whatifdelta").innerHTML = (dh != null && Math.abs(dh) > 0.004)
    ? '<span class="chip ' + (dh < 0 ? "good" : "bad") + '">' + (dh < 0 ? "▼ " : "▲ ") + nf(Math.abs(dh), 2) + ' h/day vs the calibrated case</span>'
    : '<span class="chip">calibrated case</span>';

  $("#whtkpis").innerHTML = [
    kpi(nf(row.outage_hours_per_day, 2) + " h/day", "interrupted critical supply"),
    kpi(nf(row.evening_availability_pct, 1) + "%", "evening availability, 18–23 h"),
    kpi(nf(row.lifeline_availability_pct, 1) + "%", "lifeline-circuit availability"),
    kpi("₹" + int(row.bill_inr_per_hh_month), "grid bill per household/month"),
    kpi("₹" + int(row.cost_per_hh_month_inr), "annualised asset cost per household/month"),
    kpi(int(W.bat) + " kWh", "battery in this configuration")
  ].join("");

  var sweep = WHATIF.filter(function(p){
    return Math.abs(p.pv_scale - W.pv) < 1e-9 && Math.abs(p.ev_scale - W.ev) < 1e-9 &&
           Math.abs(p.outage_mult - W.om) < 1e-9;
  }).sort(function(a, b){ return a.bat_kwh - b.bat_kwh; });
  chart("whatif", {
    type:"line",
    data:{labels:sweep.map(function(p){ return p.bat_kwh + " kWh"; }), datasets:[
      series("Interrupted critical h/day", sweep.map(function(p){ return p.outage_hours_per_day; }), T.clay,
        {borderWidth:2.4, pointRadius:4, pointBackgroundColor:T.clay, yAxisID:"y"}),
      series("Lifeline availability %", sweep.map(function(p){ return p.lifeline_availability_pct; }), T.green,
        {borderWidth:2.2, pointRadius:4, pointBackgroundColor:T.green, yAxisID:"y1", tension:.2})
    ]},
    options: base({plugins:{legend:{display:true, position:"bottom", align:"start"}, tooltip:{callbacks:{label:function(c){
      return " " + c.dataset.label + ": " + nf(c.parsed.y, 2) + (c.datasetIndex ? " %" : " h/day");
    }}}}, scales:axes({fmt:function(v){ return nf(v, 1); }, y2:true,
      y2fmt:function(v){ return nf(v, 1) + "%"; },
      yopts:{title:{display:true, text:"h/day", color:T.muted, font:{size:10}}}})}),
    plugins:[pointLabels(function(v){ return nf(v, 2); }, T.clay, 0)]
  });

  if (!dayReady) buildDaySelector();
  renderPlayer();
}
function uniq(key){
  return WHATIF.map(function(p){ return p[key]; })
    .filter(function(v, i, a){ return a.indexOf(v) === i; })
    .sort(function(a, b){ return a - b; });
}
function nearest(arr, v){
  return arr.reduce(function(a, b){ return Math.abs(b - v) < Math.abs(a - v) ? b : a; }, arr[0]);
}
function buildSeg(sel, values, fmt, key, state, redraw){
  var host = $(sel);
  if (!host) return;
  host.innerHTML = values.map(function(v){
    return '<button type="button" data-v="' + v + '" aria-pressed="' + (v === state[key]) + '">' + esc(fmt(v)) + '</button>';
  }).join("");
  host.onclick = function(e){
    var b = e.target.closest ? e.target.closest("button") : null;
    if (!b) return;
    state[key] = Number(b.dataset.v);
    $$("button", host).forEach(function(x){ x.setAttribute("aria-pressed", String(Number(x.dataset.v) === state[key])); });
    redraw();
  };
}

/* ---------- day player ---------- */
var playing = null, playerReady = false;
function initPlayer(){
  var sel = $("#pdaysel");
  if (!sel || !DAYS.length || playerReady) return;
  playerReady = true;
  sel.innerHTML = DAYS.map(function(d, i){ return '<option value="' + i + '">' + esc(d.label) + '</option>'; }).join("");
  sel.value = String(reasonIdx >= 0 ? reasonIdx : 0);
  sel.addEventListener("change", function(){ stopPlayer(); renderPlayer(); });
  var track = $("#player");
  if (track) track.addEventListener("input", renderPlayer);
  $("#playbtn").addEventListener("click", function(){
    if (playing) { stopPlayer(); return; }
    $("#playbtn").textContent = "Pause";
    playing = setInterval(function(){
      var p = $("#player");
      if (+p.value >= +p.max) { stopPlayer(); return; }
      p.value = +p.value + 1;
      renderPlayer();
    }, 200);
  });
}
function stopPlayer(){
  if (playing) { clearInterval(playing); playing = null; }
  var b = $("#playbtn");
  if (b) b.textContent = "Play 24 h";
}
function renderPlayer(){
  var sel = $("#pdaysel");
  if (!sel || !DAYS.length) return;
  initPlayer();
  var d = DAYS[Math.max(0, Math.min(DAYS.length - 1, +sel.value || 0))];
  var i = +($("#player") ? $("#player").value : 44) || 0;
  var soc = d.soc.mpc_full[i], prev = i > 0 ? d.soc.mpc_full[i - 1] : soc;
  var batt = (soc - prev) * 4;
  $("#clock").textContent = hhmm(i);
  var pack = META.bat_kwh || 100;
  $("#socread").textContent = "battery " + nf(soc, 0) + " kWh · " + nf(soc / pack * 100, 0) + "% of the " + nf(pack, 0) + " kWh pack";
  $("#playerfacts").innerHTML = [
    ["Load", nf(d.load[i], 1) + " kW"],
    ["Solar", nf(d.pv[i], 1) + " kW"],
    ["Grid import", nf(d.g.mpc_full[i], 1) + " kW"],
    ["Battery", (Math.abs(batt) < 0.05 ? "0.0" : (batt > 0 ? "+" : "−") + nf(Math.abs(batt), 1)) + " kW"],
    ["Unserved", nf(d.shed.mpc_full[i], 2) + " kWh"]
  ].map(function(f){ return '<div>' + f[0] + '<b>' + f[1] + '</b></div>'; }).join("");

  var track = $("#player");
  if (track) {
    var pctFill = (+track.value / +track.max) * 100;
    track.style.setProperty("--track", "linear-gradient(90deg,#4FBF8B 0 " + pctFill + "%,rgba(255,255,255,.18) " + pctFill + "% 100%)");
  }

  chart("flows", {
    type:"bar",
    data:{labels:["Solar", "Grid import", "Battery (ΔSOC)", "Load", "Unserved"],
      datasets:[{data:[d.pv[i], d.g.mpc_full[i], batt, d.load[i], -Math.abs(d.shed.mpc_full[i])],
        backgroundColor:["#E0A63F", "#7C9DD6", "#4FBF8B", "#C3CFC8", "#D4735B"],
        borderRadius:3, borderSkipped:false, maxBarThickness:22}]},
    options: base({indexAxis:"y", animation:false,
      plugins:{legend:{display:false}, tooltip:{callbacks:{label:function(c){
        return " " + nf(Math.abs(c.parsed.x), 2) + " kW" + (c.datasetIndex === 2 ? " (positive = discharging)" : "");
      }}}},
      scales:{x:{grid:{color:"rgba(233,241,236,.12)"}, border:{display:false},
          ticks:{color:"#93A89E", font:{family:MONO, size:10}}},
        y:{grid:{display:false}, border:{display:false},
          ticks:{color:"#E9F1EC", font:{family:SANS, size:10.5}}}}}),
    plugins:[barLabels(function(v){ return (v < 0 ? "−" : "") + nf(Math.abs(v), 1); }, "#E9F1EC")]
  });
}

/* ---------- method ---------- */
function drawMethod(){
  var P = META.provenance || {}, F = META.forecast || {};
  var pv = (P.pv_model || {}).validation_pvgis || {};
  var nasa = (P.observations || {}).nasa_crosscheck || {};
  $("#provcards").innerHTML =
    '<div class="card prov"><h4><span class="badge real">real</span> Observed</h4><ul>' +
      '<li>ERA5 reanalysis irradiance, temperature and wind via the Open-Meteo archive. <span>' + esc((P.observations || {}).licence || "") + '</span></li>' +
      '<li>Archived day-ahead operational forecasts with a 24 h lead, so the controller never sees the future. <span>' + esc(((P.forecasts || {}).lead_time_hours || 24)) + ' h lead</span></li>' +
      (nasa.correlation ? '<li>Cross-checked against NASA POWER: correlation ' + nf(nasa.correlation, 2) + ' over ' + int(nasa.n_hours) + ' hours.</li>' : '') +
      '<li>Tariffs and capex carry cited ranges in the assumptions table below.</li>' +
    '</ul></div>' +
    '<div class="card prov"><h4><span class="badge cited">modelled</span> Derived</h4><ul>' +
      '<li>PV built from real GHI: Erbs diffuse fraction, tilt at latitude, NOCT cell temperature, 14% system losses.</li>' +
      (pv.error_pct != null ? '<li>Annual yield checked against PVGIS: ' + nf(pv.model_kwh_per_kwp, 0) + ' vs ' + nf(pv.pvgis_kwh_per_kwp, 0) + ' kWh/kWp, ' + nf(pv.error_pct, 2) + '% error.</li>' : '') +
      '<li>Voltage and technical loss from a three-branch LinDistFlow feeder, not a full unbalanced network model.</li>' +
      '<li>Equity from metered flows per archetype, not from a stated assumption.</li>' +
    '</ul></div>' +
    '<div class="card prov"><h4><span class="badge assumption">calibrated</span> Assumed</h4><ul>' +
      '<li>Load shapes calibrated to Telangana LT-I consumption and a published Indian residential shape.</li>' +
      '<li>Outages drawn to reproduce ' + nf(META.outage_h_target, 1) + ' h/day; realised ' + nf(META.outage_h_realised, 1) + ' h/day in this replay.</li>' +
      '<li>Value of lost load at ₹60/kWh central, ₹30–124 cited range; shown as a range, not a point.</li>' +
      '<li>Cost of a community asset from cited BESS price bands.</li>' +
    '</ul></div>';

  var provHost = $("#provcards");
  if (provHost && F.load_mape_pct != null) {
    var stat = document.createElement("div");
    stat.className = "statline";
    stat.style.gridColumn = "1 / -1";
    stat.innerHTML =
      '<div><b>' + nf(F.load_mape_pct, 1) + '%</b><span>load MAPE</span></div>' +
      '<div><b>' + nf(F.pv_nmae_pct, 1) + '%</b><span>PV NMAE</span></div>' +
      '<div><b>' + nf(F.pv_coverage80_pct, 0) + '%</b><span>PV 80% band coverage</span></div>' +
      '<div><b>' + nf(F.load_coverage80_pct, 0) + '%</b><span>load 80% band coverage</span></div>';
    provHost.appendChild(stat);
    var note = document.createElement("p");
    note.className = "hint";
    note.style.gridColumn = "1 / -1";
    note.textContent = "Coverage below 80% is reported rather than hidden: the intervals are slightly too narrow on the load side, which makes the reserve more conservative than it needs to be.";
    provHost.appendChild(note);
  }

  var kinds = {};
  ASSUME.forEach(function(a){ kinds[a.kind] = (kinds[a.kind] || 0) + 1; });
  if ($("#assumecount")) $("#assumecount").textContent = ASSUME.length + " parameters, each with a source and a range";
  var order = ["all"].concat(Object.keys(kinds));
  $("#afilter").innerHTML = order.map(function(k){
    var n = k === "all" ? ASSUME.length : kinds[k];
    return '<button type="button" data-k="' + k + '" aria-pressed="' + (k === "all") + '">' +
      esc(k === "all" ? "All" : k) + '<span>' + n + '</span></button>';
  }).join("");
  $("#afilter").onclick = function(e){
    var b = e.target.closest ? e.target.closest("button") : null;
    if (!b) return;
    $$("button", this).forEach(function(x){ x.setAttribute("aria-pressed", String(x === b)); });
    renderAssumptions(b.dataset.k);
  };
  renderAssumptions("all");
}
function renderAssumptions(kind){
  var rows = ASSUME.filter(function(a){ return kind === "all" || a.kind === kind; });
  $("#assumptions").innerHTML =
    '<thead><tr><th>parameter</th><th>value</th><th>unit</th><th>kind</th><th>source</th><th>range</th></tr></thead><tbody>' +
    rows.map(function(a){
      return '<tr><td>' + esc(a.param.replace(/_/g, " ")) + '</td><td class="n">' + esc(a.value) +
        '</td><td>' + esc(a.unit) + '</td><td><span class="badge ' + esc(a.kind) + '">' + esc(a.kind) +
        '</span></td><td class="src">' + esc(a.source) + '</td><td class="n">' + esc(a.range) + '</td></tr>';
    }).join("") + '</tbody>';
}

/* ---------- chrome ---------- */
var TABS = [["overview","Overview"],["scenarios","Scenarios"],["discom","DISCOM"],
            ["equity","Equity"],["economics","Economics"],["whatif","What-if"],["method","Method"]];
var draw = {overview:drawOverview, scenarios:drawScenarios, discom:drawDiscom, equity:drawEquity,
            economics:drawEconomics, whatif:drawWhatIf, method:drawMethod};
var current = null;

function buildNav(){
  $("#nav").innerHTML = TABS.map(function(t, i){
    return '<button type="button" class="tabbtn" role="tab" id="b-' + t[0] + '" data-t="' + t[0] +
      '" aria-controls="t-' + t[0] + '" aria-selected="false" tabindex="-1">' +
      '<span class="n">' + ("0" + (i + 1)).slice(-2) + '</span>' + t[1] + '</button>';
  }).join("");

  $("#nav").addEventListener("click", function(e){
    var b = e.target.closest ? e.target.closest("button") : null;
    if (b && b.dataset.t) show(b.dataset.t);
  });
  $("#nav").addEventListener("keydown", function(e){
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft" && e.key !== "Home" && e.key !== "End") return;
    var names = TABS.map(function(t){ return t[0]; });
    var at = names.indexOf(current);
    if (e.key === "Home") at = 0;
    else if (e.key === "End") at = names.length - 1;
    else at = (at + (e.key === "ArrowRight" ? 1 : -1) + names.length) % names.length;
    e.preventDefault();
    show(names[at]);
    var btn = $("#b-" + names[at]);
    if (btn) btn.focus();
  });
}

function show(name){
  if (!draw[name]) name = "overview";
  var panel = $("#t-" + name);
  if (!panel) return;
  $$(".tab").forEach(function(el){ el.classList.toggle("on", el.id === "t-" + name); });
  $$(".tabbtn").forEach(function(b){
    var on = b.dataset.t === name;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
  });
  current = name;
  try {
    if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  } catch (err) { /* file:// in some browsers: hash routing is a nicety, not a requirement */ }
  draw[name]();
}

function boot(){
  if (!hasRun) { emptyState(); return; }
  chartDefaults();
  if ($("#sitemeta")) {
    $("#sitemeta").textContent = (META.site || "neighbourhood") + " · " +
      (META.start || "–") + " – " + (META.end || "–") + " · " + (META.test_days || "–") + " held-out days";
  }
  if ($("#footmeta")) {
    $("#footmeta").textContent = (META.site || "GridFlex") + " · " + (META.n_hh || "–") + " homes · " +
      (META.pv_kwp || "–") + " kWp PV · " + (META.bat_kwh || "–") + " kWh battery · built " + (META.generated || "–");
  }
  buildNav();
  initPlayer();
  var start = (location.hash || "").replace("#", "");
  show(draw[start] ? start : "overview");

  window.addEventListener("hashchange", function(){
    var n = (location.hash || "").replace("#", "");
    if (n && n !== current && draw[n]) show(n);
  });

  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var rerender = function(){
      T = tokens();
      chartDefaults();
      if (current && draw[current]) draw[current]();
    };
    if (mq.addEventListener) mq.addEventListener("change", rerender);
    else if (mq.addListener) mq.addListener(rerender);
  }
}

function emptyState(){
  var main = $("#main");
  if (!main) return;
  main.innerHTML = '<div class="wrap"><div class="empty">' +
    '<span class="mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none" style="width:22px;height:22px"><path d="M18 4L8 18h6l-1 10L24 13h-6l1-9z" fill="#fff"/></svg></span>' +
    '<h2>No results in this page yet</h2>' +
    '<p>This is the dashboard shell. It fills itself from a results payload written by <code>python run.py</code>.</p>' +
    '<p class="hint">If you opened a page from a completed run, the payload is missing — rebuild both files with <code>make_dashboard</code>. The numbers are always also in <code>outputs/results.json</code>.</p>' +
    '</div></div>';
  var nav = $("#nav");
  if (nav) nav.innerHTML = "";
}

function go(){
  if (typeof Chart === "undefined") {
    var main = $("#main");
    if (main) main.innerHTML = '<div class="wrap"><div class="empty"><h2>The chart library did not load</h2>' +
      '<p>This page inlines Chart.js at build time. Rebuild it with <code>make_dashboard</code>; the raw numbers stay available in <code>outputs/results.json</code>.</p></div></div>';
    return;
  }
  boot();
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go);
else go();
})();
</script>
</body></html>"""


def render(payload, chart_js):
    """Return the finished page: library inlined, payload embedded, nothing fetched."""
    page = PAGE.replace('<script src="chart.umd.min.js"></script>',
                        "<script>" + chart_js + "</script>")
    return page.replace("__DATA__", json.dumps(payload, default=float))
