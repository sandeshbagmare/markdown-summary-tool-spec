"""Generate 30 live samples: 15 markdown summaries + 15 visualizations in parallel."""
import json, os, sys, time, random, concurrent.futures, html, textwrap
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from markdown_summary_tool.tools.summarize_tool import create_markdown_summary
from visualization_tool.tool import create_visualization

# --- Dataset generators ---
def gen_orders(n, seed=42):
    rng = random.Random(seed)
    regions = ["East","West","North","South"]
    customers = [f"Customer_{i:04d}" for i in range(80)]
    cats = ["Electronics","Books","Clothing","Food","Toys"]
    rows=[]
    for i in range(n):
        rows.append({
            "order_id": f"O{i:06d}",
            "customer": rng.choice(customers),
            "amount": round(rng.uniform(5, 2000),2),
            "region": rng.choice(regions),
            "category": rng.choice(cats),
            "quantity": rng.randint(1,10),
            "discount": round(rng.uniform(0,0.3),2),
            "date": f"2026-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
            "status": rng.choice(["shipped","pending","cancelled","returned"]),
        })
    return rows

def gen_products(n, seed=99):
    rng = random.Random(seed)
    cats = ["Electronics","Books","Clothing","Food","Toys"]
    rows=[]
    for i in range(n):
        rows.append({
            "sku": f"SKU{i:06d}",
            "category": rng.choice(cats),
            "price": round(rng.uniform(5,3000),2),
            "stock": rng.randint(0,500),
            "rating": round(rng.uniform(1,5),1),
            "supplier": rng.choice(["Acme","Globex","Initech","Umbrella"]),
        })
    return rows

def gen_sales_timeseries(n, seed=7):
    rng = random.Random(seed)
    rows=[]
    for i in range(n):
        month = (i % 12)+1
        rows.append({
            "month": f"2026-{month:02d}",
            "revenue": round(rng.uniform(20000,120000),2),
            "orders": rng.randint(80,400),
            "region": rng.choice(["East","West","North","South"]),
        })
    return rows

# Pre-generate datasets
ORDERS_2K = gen_orders(2000, seed=42)
ORDERS_500 = gen_orders(500, seed=43)
PRODUCTS_800 = gen_products(800, seed=99)
PRODUCTS_300 = gen_products(300, seed=100)
SALES_365 = gen_sales_timeseries(365, seed=7)

def ds(*refs):
    return json.dumps(list(refs))

# --- 15 Markdown queries (medium-hard to very hard) ---
MD_QUERIES = [
    ("MD-01 — Regional revenue breakdown", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Summarize total revenue, average order value, and order count grouped by region. Highlight the top region and the spread between highest and lowest."),
    ("MD-02 — Category profitability", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Analyze total amount and average discount by category. Which category drives the most revenue and which has the highest discount rate?"),
    ("MD-03 — Customer concentration (hard)", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Identify the top 5 customers by total spend, their share of total revenue, and the long-tail distribution. Is revenue concentrated?"),
    ("MD-04 — Multi-dataset: orders + products", ds({"kind":"inline_json","name":"orders","data":ORDERS_500},{"kind":"inline_json","name":"products","data":PRODUCTS_300}), "Summarize orders and products together: compare order categories vs product categories on price, stock, and rating. Note any mismatches."),
    ("MD-05 — Time trend (monthly)", ds({"kind":"inline_json","name":"sales","data":SALES_365}), "Summarize revenue and order volume by month. Describe the trend, peak month, and lowest month with exact figures."),
    ("MD-06 — Discount impact (hard)", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Quantify the relationship between discount and amount: average amount by discount bucket, and whether higher discounts correlate with larger orders."),
    ("MD-07 — Status & returns analysis", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Break down orders by status (shipped/pending/cancelled/returned). What share is returned or cancelled and what is the revenue at risk?"),
    ("MD-08 — Quantity vs amount", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Summarize quantity and amount distributions: average quantity per order, total units sold, and average amount per unit by region."),
    ("MD-09 — Supplier & stock risk", ds({"kind":"inline_json","name":"products","data":PRODUCTS_800}), "Summarize stock and price by supplier and category. Flag low-stock high-price items and supplier concentration."),
    ("MD-10 — Outlier & tail (very hard)", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Detect outliers in amount: top 1% threshold, max order, and how much the top 10 orders contribute to total revenue. Comment on skew."),
    ("MD-11 — Regional + category cross-tab (hard)", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Cross-tabulate revenue by region and category. Which region-category cell is strongest and which is weakest?"),
    ("MD-12 — Rating vs price (products)", ds({"kind":"inline_json","name":"products","data":PRODUCTS_800}), "Summarize rating and price by category. Is there a correlation between price and rating? Give averages per category."),
    ("MD-13 — Large multi-dataset stress", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K},{"kind":"inline_json","name":"products","data":PRODUCTS_800},{"kind":"inline_json","name":"sales","data":SALES_365}), "Summarize all three datasets (orders, products, sales) together: totals, averages, and key comparisons across them."),
    ("MD-14 — Date & seasonality (hard)", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Analyze orders by date: busiest month, average amount by month, and any seasonal pattern in volume or value."),
    ("MD-15 — Full audit (very hard)", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K},{"kind":"inline_json","name":"products","data":PRODUCTS_800}), "Provide a full audit: row counts, nulls, distinct customers/categories, revenue totals, and top anomalies across both datasets."),
]

# --- 15 Visualization queries ---
VIZ_QUERIES = [
    ("VZ-01 — Bar: revenue by region", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Bar chart of total amount by region", "bar"),
    ("VZ-02 — Line: revenue over time", ds({"kind":"inline_json","name":"sales","data":SALES_365}), "Line chart showing revenue trend over month", "line"),
    ("VZ-03 — Pie: share by category", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Pie chart of revenue share by category", "pie"),
    ("VZ-04 — Scatter: price vs rating", ds({"kind":"inline_json","name":"products","data":PRODUCTS_800}), "Scatter plot of price vs rating colored by category", "scatter"),
    ("VZ-05 — Bar: stock by supplier", ds({"kind":"inline_json","name":"products","data":PRODUCTS_800}), "Bar chart of total stock by supplier", "bar"),
    ("VZ-06 — Bar: orders by status", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Bar chart of order count by status", "bar"),
    ("VZ-07 — Line: orders over month", ds({"kind":"inline_json","name":"sales","data":SALES_365}), "Line chart of orders over month", "line"),
    ("VZ-08 — Pie: region distribution", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Pie chart showing distribution of orders by region", "pie"),
    ("VZ-09 — Scatter: amount vs quantity", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Scatter plot of amount vs quantity", "scatter"),
    ("VZ-10 — Bar: avg discount by category", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Bar chart of average discount by category", "bar"),
    ("VZ-11 — Auto: revenue by category", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Show revenue by category", "auto"),
    ("VZ-12 — Bar: rating by category", ds({"kind":"inline_json","name":"products","data":PRODUCTS_800}), "Bar chart of average rating by category", "bar"),
    ("VZ-13 — Line: monthly revenue (orders)", ds({"kind":"inline_json","name":"orders","data":ORDERS_2K}), "Line chart of revenue trend over date", "line"),
    ("VZ-14 — Pie: stock share by category", ds({"kind":"inline_json","name":"products","data":PRODUCTS_800}), "Pie chart of stock share by category", "pie"),
    ("VZ-15 — Scatter: stock vs price", ds({"kind":"inline_json","name":"products","data":PRODUCTS_800}), "Scatter plot of stock vs price", "scatter"),
]

def call_md(item):
    title, datasets_json, question = item
    t0=time.perf_counter()
    raw = create_markdown_summary.invoke({"datasets_json": datasets_json, "question": question}) if hasattr(create_markdown_summary,"invoke") else create_markdown_summary(datasets_json, question)
    elapsed=time.perf_counter()-t0
    parsed=json.loads(raw)
    return (title, question, parsed, elapsed)

def call_vz(item):
    title, datasets_json, question, chart_type = item
    t0=time.perf_counter()
    raw = create_visualization.invoke({"datasets_json": datasets_json, "question": question, "chart_type": chart_type}) if hasattr(create_visualization,"invoke") else create_visualization(datasets_json, question, chart_type)
    elapsed=time.perf_counter()-t0
    parsed=json.loads(raw)
    return (title, question, chart_type, parsed, elapsed)

print("Firing 30 parallel tool calls (15 MD + 15 VZ) ...")
all_results_md=[]
all_results_vz=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
    fut_md = {ex.submit(call_md, q): q[0] for q in MD_QUERIES}
    fut_vz = {ex.submit(call_vz, q): q[0] for q in VIZ_QUERIES}
    for fut in concurrent.futures.as_completed(list(fut_md.keys())+list(fut_vz.keys())):
        try:
            res=fut.result()
            if len(res)==4:
                all_results_md.append(res)
                print(f"  MD done: {res[0]}  elapsed={res[3]:.2f}s  verified={res[2].get('meta',{}).get('verified')} facts={len(res[2].get('facts',[]))}")
            else:
                all_results_vz.append(res)
                print(f"  VZ done: {res[0]}  elapsed={res[4]:.2f}s  chart_type={res[2]} rows={res[3].get('meta',{}).get('row_count')}")
        except Exception as e:
            print(f"  ERROR: {e}")

# Sort back to original order
order_md = {q[0]:i for i,q in enumerate(MD_QUERIES)}
order_vz = {q[0]:i for i,q in enumerate(VIZ_QUERIES)}
all_results_md.sort(key=lambda x: order_md[x[0]])
all_results_vz.sort(key=lambda x: order_vz[x[0]])

# Save raw JSON
with open(os.path.join(os.path.dirname(__file__), "samples_raw.json"), "w", encoding="utf-8") as f:
    json.dump({"markdown": [{"title":t,"question":q,"elapsed":e,"result":r} for t,q,r,e in all_results_md],
               "visualizations": [{"title":t,"question":q,"chart_type":ct,"elapsed":e,"result":r} for t,q,ct,r,e in all_results_vz]}, f, indent=2, ensure_ascii=False)

print(f"\nDone: {len(all_results_md)} MD + {len(all_results_vz)} VZ")
# Build HTML
import html as h

def md_to_html(md_text):
    # minimal markdown to html: headers, bold, lists, code
    lines=md_text.split("\n")
    out=[]
    in_list=False
    for line in lines:
        s=line.strip()
        if s.startswith("## "):
            if in_list: out.append("</ul>"); in_list=False
            out.append(f"<h3>{h.escape(s[3:])}</h3>")
        elif s.startswith("# "):
            if in_list: out.append("</ul>"); in_list=False
            out.append(f"<h2>{h.escape(s[2:])}</h2>")
        elif s.startswith("- "):
            if not in_list: out.append("<ul>"); in_list=True
            txt=h.escape(s[2:])
            # bold
            import re
            txt=re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", txt)
            out.append(f"<li>{txt}</li>")
        elif s.startswith("_") and s.endswith("_") and len(s)>2:
            if in_list: out.append("</ul>"); in_list=False
            out.append(f"<p><em>{h.escape(s[1:-1])}</em></p>")
        elif s=="":
            if in_list: out.append("</ul>"); in_list=False
            out.append("")
        else:
            if in_list: out.append("</ul>"); in_list=False
            import re
            txt=h.escape(line)
            txt=re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", txt)
            if txt.strip():
                out.append(f"<p>{txt}</p>")
    if in_list: out.append("</ul>")
    return "\n".join(out)

# Build HTML file
html_path = os.path.join(os.path.dirname(__file__), "samples_30.html")
parts=[]
parts.append("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>30 Live Samples — Markdown Summary + Visualization</title>
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
<style>
*{box-sizing:border-box} body{font-family:Inter,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
header{position:sticky;top:0;z-index:10;background:#0f172aee;backdrop-filter:blur(8px);border-bottom:1px solid #1e293b;padding:18px 24px}
header h1{margin:0;font-size:22px;letter-spacing:.2px}
header p{margin:6px 0 0;color:#94a3b8;font-size:13px}
nav{padding:12px 24px;display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid #1e293b;background:#0b1224}
nav a{font-size:12px;padding:6px 10px;border-radius:999px;background:#1e293b;color:#cbd5e1;text-decoration:none}
nav a:hover{background:#334155;color:#fff}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:18px}
@media(max-width:1100px){.grid{grid-template-columns:1fr}}
.card{background:#111c33;border:1px solid #1e293b;border-radius:16px;overflow:hidden;box-shadow:0 6px 24px rgba(0,0,0,.25)}
.card h2{margin:0;padding:14px 16px;font-size:14px;background:#0b1224;border-bottom:1px solid #1e293b;display:flex;justify-content:space-between;align-items:center;gap:8px}
.badge{font-size:11px;padding:4px 8px;border-radius:999px;background:#1e293b;color:#93c5fd;white-space:nowrap}
.badge.ok{background:#064e3b;color:#6ee7b7}
.badge.warn{background:#7c2d12;color:#fdba74}
.meta{padding:10px 16px;font-size:11px;color:#94a3b8;display:flex;gap:12px;flex-wrap:wrap;border-bottom:1px solid #1e293b;background:#0f1a33}
.body{padding:16px}
.body h3{margin:14px 0 8px;font-size:14px;color:#f1f5f9}
.body p{margin:6px 0;line-height:1.5;font-size:13px;color:#cbd5e1}
.body ul{margin:6px 0 10px 18px}
.body li{margin:4px 0;font-size:13px}
.facts{margin-top:12px;border:1px solid #1e293b;border-radius:10px;overflow:hidden}
.facts summary{cursor:pointer;padding:10px 12px;background:#0b1224;font-size:12px;color:#93c5fd}
.facts pre{margin:0;padding:12px;max-height:220px;overflow:auto;background:#0a1228;color:#cbd5e1;font-size:11px}
.vega{width:100%;min-height:260px;background:#fff;border-radius:10px;padding:8px}
.q{font-size:12px;color:#94a3b8;margin:0 0 8px;font-style:italic}
.kbd{font-family:ui-monospace,monospace;font-size:11px;background:#1e293b;padding:2px 6px;border-radius:6px}
footer{padding:18px 24px;color:#64748b;font-size:12px;border-top:1px solid #1e293b}
</style></head><body>
<header><h1>30 Live Samples — <span style="color:#93c5fd">Markdown Summary</span> + <span style="color:#6ee7b7">Visualization</span></h1>
<p>15 × <code>create_markdown_summary</code> (medium → very hard) + 15 × <code>create_visualization</code> — all executed <strong>live &amp; in parallel</strong> via the DeepAgent tools (DuckDB + MockLLM + Vega-Lite). Generated """+time.strftime("%Y-%m-%d %H:%M")+" — iframe-ready.</p></header>")
parts.append('<nav>')
for t,_,_,_ in all_results_md:
    parts.append(f'<a href="#{h.escape(t).replace(" ","-")}">{h.escape(t)}</a>')
for t,_,_,_,_ in all_results_vz:
    parts.append(f'<a href="#{h.escape(t).replace(" ","-")}">{h.escape(t)}</a>')
parts.append('</nav>')
parts.append('<div class="grid">')

# MD cards
for title, question, parsed, elapsed in all_results_md:
    md = parsed.get("markdown","")
    facts = parsed.get("facts",[])
    warnings = parsed.get("warnings",[])
    meta = parsed.get("meta",{})
    verified = meta.get("verified")
    anchor = h.escape(title).replace(" ","-")
    badge = '<span class="badge ok">verified ✓</span>' if verified else '<span class="badge warn">unverified</span>' if verified is False else '<span class="badge">no verify</span>'
    md_html = md_to_html(md) if md else "<p><em>No markdown</em></p>"
    facts_json = h.escape(json.dumps(facts[:8], indent=2, ensure_ascii=False)) if facts else "[]"
    warnings_html = "".join(f"<div style='color:#fdba74;font-size:11px'>⚠ {h.escape(w)}</div>" for w in warnings[:3])
    parts.append(f"""
<section class="card" id="{anchor}">
<h2>{h.escape(title)} {badge}</h2>
<div class="meta"><span>⏱ {elapsed*1000:.0f} ms</span><span>facts: {len(facts)}</span><span>verified: {verified}</span><span>warnings: {len(warnings)}</span></div>
<div class="body">
<p class="q">Q: {h.escape(question)}</p>
{warnings_html}
{md_html}
<details class="facts"><summary>Show facts JSON (first 8)</summary><pre>{facts_json}</pre></details>
</div></section>""")

# VZ cards
for idx,(title, question, chart_type, parsed, elapsed) in enumerate(all_results_vz):
    meta = parsed.get("meta",{})
    warnings = parsed.get("warnings",[])
    spec = parsed.get("chart_spec",{})
    spec_json = json.dumps(spec, ensure_ascii=False)
    spec_escaped = h.escape(spec_json)
    anchor = h.escape(title).replace(" ","-")
    div_id = f"vis-{idx}"
    warnings_html = "".join(f"<div style='color:#fdba74;font-size:11px'>⚠ {h.escape(w)}</div>" for w in warnings[:3])
    parts.append(f"""
<section class="card" id="{anchor}">
<h2>{h.escape(title)} <span class="badge">{h.escape(str(meta.get('chart_type',chart_type)))}</span></h2>
<div class="meta"><span>⏱ {elapsed*1000:.0f} ms</span><span>rows: {meta.get('row_count','?')}</span><span>x: {h.escape(str(meta.get('x_field','')))}</span><span>y: {h.escape(str(meta.get('y_field','')))}</span></div>
<div class="body">
<p class="q">Q: {h.escape(question)} — <span class="kbd">{h.escape(chart_type)}</span></p>
{warnings_html}
<div id="{div_id}" class="vega"></div>
<details class="facts"><summary>Show Vega-Lite spec</summary><pre>{spec_escaped}</pre></details>
</div></section>
<script>(function(){{ const spec={spec_json}; vegaEmbed('#{div_id}', spec, {{actions:false}}).catch(e=>{{document.getElementById('{div_id}').innerHTML='<pre style=color:#ef4444>'+e.message+'</pre>'}}); }})();</script>
""")

parts.append('</div>')
parts.append(f'<footer>Generated live via <code>create_markdown_summary</code> + <code>create_visualization</code> (DuckDB push-down, MockLLM verbalization, mechanical verifier, Vega-Lite). All 30 calls fired in parallel with ThreadPoolExecutor(15). Raw JSON: <code>outputs/samples_raw.json</code> — HTML is iframe-ready (just &lt;iframe src="samples_30.html"&gt;).</footer>')
parts.append('</body></html>')
with open(html_path, "w", encoding="utf-8") as f:
    f.write("\n".join(parts))
print(f"HTML written to {html_path}  size={os.path.getsize(html_path)} bytes")
