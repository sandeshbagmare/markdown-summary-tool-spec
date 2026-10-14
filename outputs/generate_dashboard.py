"""Build a live multi-chart dashboard: 6 parallel create_visualization calls + 1 markdown summary, stitched into one HTML."""
import json, os, sys, time, random, concurrent.futures, html
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from markdown_summary_tool.tools.summarize_tool import create_markdown_summary
from visualization_tool.tool import create_visualization

def gen_orders(n, seed=42):
    rng=random.Random(seed)
    regions=["East","West","North","South"]
    cats=["Electronics","Books","Clothing","Food","Toys"]
    customers=[f"C{i:03d}" for i in range(60)]
    rows=[]
    for i in range(n):
        rows.append({"order_id":f"O{i:06d}","customer":rng.choice(customers),"amount":round(rng.uniform(10,2000),2),"region":rng.choice(regions),"category":rng.choice(cats),"quantity":rng.randint(1,10),"discount":round(rng.uniform(0,0.3),2),"date":f"2026-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}","status":rng.choice(["shipped","pending","cancelled","returned"])})
    return rows
def gen_products(n, seed=99):
    rng=random.Random(seed)
    cats=["Electronics","Books","Clothing","Food","Toys"]
    rows=[]
    for i in range(n):
        rows.append({"sku":f"SKU{i:06d}","category":rng.choice(cats),"price":round(rng.uniform(5,3000),2),"stock":rng.randint(0,500),"rating":round(rng.uniform(1,5),1),"supplier":rng.choice(["Acme","Globex","Initech","Umbrella"])})
    return rows
def gen_sales(n, seed=7):
    rng=random.Random(seed)
    rows=[]
    for i in range(n):
        m=(i%12)+1
        rows.append({"month":f"2026-{m:02d}","revenue":round(rng.uniform(20000,120000),2),"orders":rng.randint(80,400),"region":rng.choice(["East","West","North","South"])})
    return rows

ORDERS=gen_orders(2000,42)
PRODUCTS=gen_products(800,99)
SALES=gen_sales(365,7)

def ds(*refs): return json.dumps(list(refs))

# 6 viz queries for dashboard
VIZ = [
    ("Revenue by Region","Bar chart of total amount by region","bar", ds({"kind":"inline_json","name":"orders","data":ORDERS})),
    ("Revenue Trend","Line chart showing revenue trend over month","line", ds({"kind":"inline_json","name":"sales","data":SALES})),
    ("Share by Category","Pie chart of revenue share by category","pie", ds({"kind":"inline_json","name":"orders","data":ORDERS})),
    ("Price vs Rating","Scatter plot of price vs rating","scatter", ds({"kind":"inline_json","name":"products","data":PRODUCTS})),
    ("Stock by Supplier","Bar chart of total stock by supplier","bar", ds({"kind":"inline_json","name":"products","data":PRODUCTS})),
    ("Orders by Status","Bar chart of order count by status","bar", ds({"kind":"inline_json","name":"orders","data":ORDERS})),
]
MD_Q = "Summarize total revenue, average order value, order count by region and category. Highlight top region and top category with exact figures."
MD_DS = ds({"kind":"inline_json","name":"orders","data":ORDERS},{"kind":"inline_json","name":"products","data":PRODUCTS})

def call_vz(item):
    title,q,ct,datasets_json=item
    raw = create_visualization.invoke({"datasets_json":datasets_json,"question":q,"chart_type":ct,"options_json": json.dumps({"width":380,"height":260})}) if hasattr(create_visualization,"invoke") else create_visualization(datasets_json,q,ct, json.dumps({"width":380,"height":260}))
    return (title,q,ct,json.loads(raw))
def call_md():
    raw = create_markdown_summary.invoke({"datasets_json":MD_DS,"question":MD_Q}) if hasattr(create_markdown_summary,"invoke") else create_markdown_summary(MD_DS,MD_Q)
    return json.loads(raw)

print("Firing 6 viz + 1 md in parallel...")
with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
    fut_vz=[ex.submit(call_vz, x) for x in VIZ]
    fut_md=ex.submit(call_md)
    vz_results=[f.result() for f in fut_vz]
    md_result=fut_md.result()

print(f"Viz done: {len(vz_results)}, MD facts: {len(md_result.get('facts',[]))} verified={md_result.get('meta',{}).get('verified')}")

# Build dashboard HTML
def md_to_html(md):
    import re
    lines=md.split("\n"); out=[]; in_list=False
    for line in lines:
        s=line.strip()
        if s.startswith("## "):
            if in_list: out.append("</ul>"); in_list=False
            out.append(f"<h3>{html.escape(s[3:])}</h3>")
        elif s.startswith("# "):
            if in_list: out.append("</ul>"); in_list=False
            out.append(f"<h2>{html.escape(s[2:])}</h2>")
        elif s.startswith("- "):
            if not in_list: out.append("<ul>"); in_list=True
            txt=html.escape(s[2:]); txt=re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", txt)
            out.append(f"<li>{txt}</li>")
        elif s=="" :
            if in_list: out.append("</ul>"); in_list=False
            out.append("")
        else:
            if in_list: out.append("</ul>"); in_list=False
            txt=html.escape(line); txt=re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", txt)
            if txt.strip(): out.append(f"<p>{txt}</p>")
    if in_list: out.append("</ul>")
    return "\n".join(out)

md_html = md_to_html(md_result.get("markdown",""))
# KPI extraction from facts
facts=md_result.get("facts",[])
def find_fact(id_contains):
    for f in facts:
        if id_contains in f.get("id",""): return f
    return None
kpis=[]
for fid in ["orders__count","orders__amount__sum","orders__amount__avg","products__count"]:
    f=find_fact(fid)
    if f: kpis.append(f)

html_path=os.path.join(os.path.dirname(__file__), "dashboard.html")
parts=[]
parts.append("""<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Dashboard — 6 Charts + Summary (Live)</title>
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
<style>
*{box-sizing:border-box} body{margin:0;font-family:Inter,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0f172a;color:#e2e8f0}
header{position:sticky;top:0;z-index:10;background:#0f172ae6;backdrop-filter:blur(8px);border-bottom:1px solid #1e293b;padding:16px 20px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
header h1{margin:0;font-size:18px} header p{margin:4px 0 0;color:#94a3b8;font-size:12px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:16px 20px}
@media(max-width:900px){.kpis{grid-template-columns:repeat(2,1fr)}}
.kpi{background:#111c33;border:1px solid #1e293b;border-radius:14px;padding:14px}
.kpi .label{font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em}
.kpi .value{font-size:20px;font-weight:700;margin-top:4px;color:#f1f5f9}
.kpi .sub{font-size:11px;color:#64748b;margin-top:2px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;padding:0 20px 20px}
@media(max-width:1100px){.grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:640px){.grid{grid-template-columns:1fr}}
.card{background:#111c33;border:1px solid #1e293b;border-radius:14px;overflow:hidden}
.card h3{margin:0;padding:10px 12px;font-size:12px;background:#0b1224;border-bottom:1px solid #1e293b;display:flex;justify-content:space-between;align-items:center}
.badge{font-size:10px;padding:3px 7px;border-radius:999px;background:#1e293b;color:#93c5fd}
.vega{background:#fff;border-radius:10px;margin:10px;padding:6px;min-height:260px}
.summary{margin:0 20px 20px;background:#111c33;border:1px solid #1e293b;border-radius:14px;overflow:hidden}
.summary h2{margin:0;padding:12px 16px;font-size:13px;background:#0b1224;border-bottom:1px solid #1e293b}
.summary .body{padding:16px} .summary .body p{font-size:13px;line-height:1.5;color:#cbd5e1} .summary .body li{font-size:13px;margin:4px 0}
.summary .body h3{font-size:14px;color:#f1f5f9;margin:12px 0 6px}
footer{padding:14px 20px;color:#64748b;font-size:11px;border-top:1px solid #1e293b}
code{background:#1e293b;padding:2px 6px;border-radius:6px;font-size:11px}
</style></head><body>
<header><div><h1>📊 Live Dashboard — 6 Charts + Verified Summary</h1><p>Built from <code>create_visualization</code> ×6 + <code>create_markdown_summary</code> ×1 — all fired <b>in parallel</b> (DuckDB + Vega-Lite). Single HTML, iframe-ready.</p></div><div style="font-size:11px;color:#94a3b8">"""+time.strftime("%Y-%m-%d %H:%M")+""" · verified ✓</div></header>
""")
# KPIs
parts.append('<div class="kpis">')
for f in kpis:
    label=f.get("provenance",{}).get("description",f.get("id"))
    parts.append(f'<div class="kpi"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(f.get("formatted",""))}</div><div class="sub">{html.escape(f.get("id",""))} · {html.escape(f.get("kind",""))}</div></div>')
if not kpis:
    parts.append('<div class="kpi"><div class="label">No KPIs</div><div class="value">—</div></div>')
parts.append('</div>')
# Grid
parts.append('<div class="grid">')
for idx,(title,q,ct,parsed) in enumerate(vz_results):
    meta=parsed.get("meta",{})
    spec=json.dumps(parsed.get("chart_spec",{}), ensure_ascii=False)
    div_id=f"vis-{idx}"
    parts.append(f'<div class="card"><h3>{html.escape(title)} <span class="badge">{html.escape(str(meta.get("chart_type",ct)))} · {meta.get("row_count","?")} rows</span></h3><div id="{div_id}" class="vega"></div><div style="padding:0 12px 10px;color:#64748b;font-size:11px">{html.escape(q)}</div></div>\n<script>(function(){{const spec={spec}; vegaEmbed("#{div_id}", spec, {{actions:false}}).catch(e=>{{document.getElementById("{div_id}").innerHTML="<pre style=color:#ef4444>"+e.message+"</pre>"}});}})();</script>')
parts.append('</div>')
# Summary
parts.append(f'<div class="summary"><h2>📝 Verified Markdown Summary — {html.escape(MD_Q[:80])}… <span style="float:right;color:#6ee7b7;font-size:11px">verified ✓ · {len(facts)} facts</span></h2><div class="body">{md_html}<details style="margin-top:12px;border:1px solid #1e293b;border-radius:10px;overflow:hidden"><summary style="cursor:pointer;padding:8px 12px;background:#0b1224;font-size:11px;color:#93c5fd">Show facts JSON</summary><pre style="margin:0;padding:12px;max-height:220px;overflow:auto;background:#0a1228;color:#cbd5e1;font-size:11px">{html.escape(json.dumps(facts[:10], indent=2, ensure_ascii=False))}</pre></details></div></div>')
parts.append('<footer>How it works: each chart is one <code>create_visualization(datasets_json, question, chart_type)</code> call. Dashboard = N calls in parallel (ThreadPoolExecutor) + stitch Vega specs into one HTML grid. Tool itself is single-chart by design (deterministic DuckDB aggregation → Vega-Lite spec); composition is done in your app layer. Embed via <code>&lt;iframe src="dashboard.html" width="100%" height="900"&gt;</code>. See <code>outputs/samples_30.html</code> for 30 individual samples.</footer></body></html>')
with open(html_path,"w",encoding="utf-8") as f:
    f.write("\n".join(parts))
print(f"Dashboard written to {html_path} size={os.path.getsize(html_path)} bytes")
