"""Publication content. Cross-references use @@key@@ and are resolved to page links at build time."""
import diagrams as D
from layout import chip, ctitle, table, title
from model import ADRS, FINDINGS, GLOSSARY, MODULES, PROPOSED_DECISIONS, REPO, ROADMAP, TESTRUN
from svg import C, STATUS, icon

R = lambda k: f"@@{k}@@"  # noqa: E731


def fig(d, crop=None):
    if crop is None:
        crop = 0 if d.dark else 30
    return f'<div class="fig">{d.svg(crop=crop)}</div>'


def interp(how, refs):
    return f'<div class="interp"><div class="k">How to read</div><div>{how} <span class="ref">→ {refs}</span></div></div>'


# ====================================================================== cover
def cover_svg():
    from svg import Diagram
    import math
    d = Diagram(1123, 794, dark=True)
    cx, cy = 820, 400
    for r, col, dash, op in [(330, "#1E4468", "2 6", 0.9), (290, C["mint"], None, 0.35), (250, C["cyan"], None, 0.5), (205, C["blue"], None, 0.6),
                             (160, C["amber"], "3 4", 0.7), (110, C["purple"], None, 0.55), (62, C["cyan"], None, 0.9)]:
        d.circle(cx, cy, r, fill="none", stroke=col, sw=1.2, dash=dash, opacity=op)
    for i in range(7):
        a = math.radians(i * 360 / 7 - 90)
        x, y = cx + 160 * math.cos(a), cy + 160 * math.sin(a)
        d.circle(x, y, 5, fill=C["amber"])
    for i in range(4):
        a = math.radians(i * 90 - 45)
        x, y = cx + 250 * math.cos(a), cy + 250 * math.sin(a)
        d.circle(x, y, 6, fill=C["navy"], stroke=C["cyan"], sw=1.6)
    for i in range(6):
        a = math.radians(i * 60)
        x, y = cx + 290 * math.cos(a), cy + 290 * math.sin(a)
        d.circle(x, y, 3.4, fill=C["mint"])
    d.circle(cx, cy, 40, fill="#0A2440", stroke=C["cyan"], sw=1.6)
    d.text(cx, cy + 5, "CORE", 10, 600, C["cyan"], "middle", "mono", ls=2)
    # flight path arc
    d.raw(f'<path d="M520,700 C640,600 760,560 1123,520" fill="none" stroke="{C["amber"]}" stroke-width="1.4" stroke-dasharray="6 6" opacity="0.7"/>')
    return d.svg()


def p_cover():
    return f'''<div style="position:absolute;inset:0">{cover_svg()}</div>
<div style="position:absolute;left:16mm;top:20mm;width:150mm">
 <div style="font-family:'IBM Plex Mono';font-size:8pt;letter-spacing:.3em;color:{C['cyan']}">KOTA AEROSPACE</div>
 <div style="height:44mm"></div>
 <div style="font-family:'IBM Plex Mono';font-size:8pt;letter-spacing:.2em;color:{C['amber']};margin-bottom:5mm">ARCHITECTURE MASTER BLUEPRINT · VOLUME 1</div>
 <h1 style="font-size:40pt;line-height:1.02;font-weight:600;color:#fff">One platform <br>for aerospace <br>intelligence, <br>maintenance &amp; <br>compliance</h1>
 <p style="font-size:11pt;line-height:1.5;color:#B9CADB;margin-top:7mm;max-width:118mm">The verified current architecture, the target it should grow into, and the decisions in between — built from a code-level audit of the Aerocomply repository.</p>
</div>
<div style="position:absolute;left:16mm;bottom:14mm;display:grid;grid-template-columns:repeat(4,auto);gap:10mm;font-family:'IBM Plex Mono';font-size:7pt;letter-spacing:.1em;color:#8FA6BF">
 <div>EDITION<br><span style="color:#fff">v1.0 · 1 Oct 2026</span></div>
 <div>EVIDENCE BASE<br><span style="color:#fff">commit 6bd38ce · {REPO['branch']}</span></div>
 <div>CLASSIFICATION<br><span style="color:#fff">Internal · engineering reference</span></div>
 <div>STATUS<br><span style="color:#fff">Current verified + target, labelled</span></div>
</div>'''


# ====================================================================== contents
TOC = [
    ("FOUNDATIONS", [("01", "Reading guide & status legend", "legend"), ("02", "Executive architecture overview", "exec"), ("03", "Audit inventory & evidence", "audit"),
                     ("04", "Product vision & architectural principles", "principles")]),
    ("THE SYSTEM", [("05", "Master ecosystem map — D01", "d01"), ("06", "Suite architecture", "suites"), ("07", "Layered architecture — D02", "d02"),
                    ("08", "Backend modular monolith — D03", "d03"), ("09", "Module catalogue", "modcat"), ("10", "Domain ownership & dependency boundaries", "deps"),
                    ("11", "Infrastructure topology — D04", "d04"), ("12", "Current vs target infrastructure", "infra2"), ("13", "Data architecture & contracts", "data")]),
    ("DATA & INTELLIGENCE", [("14", "Telemetry & connectivity — D05", "d05"), ("15", "Connectivity options & dependencies", "conn2"), ("16", "HUMS processing — D06", "d06"),
                             ("17", "M7, M14-ext and M4.2 ownership — D07", "d07"), ("18", "LISA & agentic AI — D08", "d08"), ("19", "Agentic workflows", "agents")]),
    ("OPERATIONS & GOVERNANCE", [("20", "Compliance & rules engine — D09", "d09"), ("21", "MRO & asset lifecycle — D10", "d10"), ("22", "Plans & entitlements — D11", "d11"),
                                 ("23", "Security & trust boundaries — D12", "d12"), ("24", "Security controls & sovereignty", "sec2"), ("25", "Deployment topology — D13", "d13"),
                                 ("26", "Reliability & observability", "rel"), ("27", "Integration & event architecture", "events")]),
    ("SCENARIOS, STATUS & DECISIONS", [("28", "Scenario 1 — drone anomaly to maintenance", "s1"), ("29", "Scenario 2 — compliance obligation", "s2"), ("30", "Scenario 3 — subscription to access", "s3"),
                                       ("31", "Implementation status register", "status"), ("32", "Architecture gaps & corrections", "gaps"), ("33", "Recommended technical roadmap", "roadmap"),
                                       ("34", "Architecture decision register", "adrs"), ("35", "Decisions & trade-offs requiring approval", "approve"), ("36", "Glossary, legend & change history", "gloss")]),
]


def p_toc():
    col = []
    for part, items in TOC:
        col.append(f'<div class="part">{part}</div>')
        for n, t, k in items:
            col.append(f'<a href="#{k}"><span class="tn">{n}</span><span>{t}</span><span class="tp">{R(k + ":n")}</span></a>')
    half = len(col) // 2 + 2
    left = "".join(col[:half])
    right = "".join(col[half:])
    return f'''{title("", "Contents", "Volume 1", "Thirty-six sections, fourteen mandatory diagram families plus supporting views. Every diagram carries a status label; every claim of implementation is backed by code evidence or marked otherwise.")}
<div class="cols c3" style="gap:9mm;flex:1">
 <div class="toc">{left}</div><div class="toc">{right}</div>
 <div>
  <div class="card acc"><h3>Document control</h3>
   <table><tbody>
   <tr><td class="mono">Edition</td><td>v1.0 — first publication</td></tr>
   <tr><td class="mono">Date</td><td>1 October 2026</td></tr>
   <tr><td class="mono">Evidence</td><td>Aerocomply repository, branch <b>{REPO['branch']}</b>, commit <b>6bd38ce</b></td></tr>
   <tr><td class="mono">Method</td><td>Source, migrations, routes, tests, CI, docs read; backend and frontend suites re-run independently</td></tr>
   <tr><td class="mono">Not inspected</td><td>Hosted environments, production data, hardware, provider consoles</td></tr>
   <tr><td class="mono">Sources</td><td>Editable SVG / Python / Markdown in <span class="mono">docs/architecture-blueprint/</span></td></tr>
   <tr><td class="mono">Owner</td><td>[Architecture owner — to be assigned]</td></tr>
   </tbody></table></div>
  <div class="card amber" style="margin-top:5mm"><h3>Three rules this document follows</h3>
   <ul class="tight"><li>Reports are not proof: historical claims were re-checked against code.</li><li>Every diagram says whether it shows what exists, what is planned, or both.</li><li>External validation (hardware, providers, UAT, pen test) is never implied.</li></ul></div>
 </div>
</div>'''


# ====================================================================== legend
def p_legend():
    rows = []
    for k in ["VERIFIED", "PARTIAL", "DESIGNED", "PROPOSED", "EXTERNAL", "VERIFY", "SUPERSEDED"]:
        st = STATUS[k]
        dash = st["dash"] or "solid"
        rows.append([chip(k), st["long"].split(" — ")[1] if " — " in st["long"] else st["long"],
                     f'<svg width="70" height="16"><rect x="1" y="2" width="68" height="12" rx="3" fill="#fff" stroke="{st["color"]}" stroke-width="1.2" {"" if dash == "solid" else f"stroke-dasharray={chr(34)}{dash}{chr(34)}"}/></svg>'])
    from svg import ARROW
    arr = []
    for k in ["sync", "async", "data", "obs", "human", "feedback", "prohibited", "proposed"]:
        a = ARROW[k]
        dsh = f'stroke-dasharray="{a["dash"]}"' if a["dash"] else ""
        head = {"solid": f'<path d="M58,3 L66,8 L58,13 Z" fill="{a["color"]}"/>', "open": f'<path d="M58,3 L66,8 L58,13" fill="none" stroke="{a["color"]}" stroke-width="1.4"/>',
                "cross": f'<path d="M58,3 L66,13 M66,3 L58,13" stroke="{a["color"]}" stroke-width="1.6"/>'}[a["head"]]
        arr.append([f'<svg width="70" height="16"><line x1="2" y1="8" x2="64" y2="8" stroke="{a["color"]}" stroke-width="{a["width"]}" {dsh}/>{head}</svg>', a["label"]])
    kinds = [("infra", "Blue", "Infrastructure, runtime, connectivity"), ("data", "Cyan", "Data movement, ingestion, storage"), ("domain", "Teal", "Operational and domain processing"),
             ("decision", "Amber", "Evaluation, findings, signals, decisions"), ("ai", "Purple", "AI, LISA and orchestration"), ("risk", "Coral", "Warnings, exceptions, risk boundaries"),
             ("gov", "Mint", "Governance, audit, commercial control"), ("ext", "Slate", "External systems and providers")]
    from svg import KIND
    krows = [[f'<span style="display:inline-block;width:22px;height:10px;border-radius:2px;background:{KIND[k][0]}"></span>', n, t] for k, n, t in kinds]
    return f'''{title("01", "Reading guide &amp; status legend", "How to read this blueprint", "One visual language is used on every page. Status is encoded three ways — icon, label and border style — so it survives greyscale printing. Colour carries meaning, never decoration.")}
<div class="cols c3" style="flex:1">
 <div><h3>Implementation status</h3>{table(["Label", "Meaning", "Border"], rows, ["30%", "50%", "20%"])}
  <p class="small" style="margin-top:3mm">A component is <b>VERIFIED</b> only when code, a migration (where data is involved) and a passing test were found. Documents alone never earn VERIFIED.</p></div>
 <div><h3>Connectors</h3>{table(["Line", "Meaning"], arr, ["32%", "68%"])}
  <h3 style="margin-top:4mm">Diagram scope labels</h3>
  <p class="small"><span class="tag cur">CURRENT VERIFIED</span> what the code does today<br><br><span class="tag tgt">TARGET / PROPOSED</span> recommended, not built<br><br><span class="tag hyb">HYBRID</span> both, distinguished by status per element</p></div>
 <div><h3>Semantic colour</h3>{table(["", "Colour", "Used for"], krows, ["14%", "18%", "68%"])}
  <div class="card coral" style="margin-top:4mm"><h3>Numbered callouts</h3><p class="small">Amber, cyan and mint discs on diagrams map to explanation lists and page references. Mono text in boxes is the repository path or table that proves the element.</p></div></div>
</div>'''


# ====================================================================== executive
def p_exec():
    stats = [("2 689", "backend tests passed in this audit's independent run (1 failed — test race)"), ("383", "frontend unit tests passed (vitest, 37 files)"),
             ("70", "Alembic migrations — clean upgrade 0001 → 0070 on empty PostgreSQL 16"), ("61", "LISA tools, each gated by permission + suite + feature"),
             ("4", "suites on one core: Aircraft, Drone/UAV, Helicopter, eVTOL/AAM"), ("0", "hardware, provider or customer validations performed — all EXTERNAL")]
    st = "".join(f'<div class="stat"><div class="v">{v}</div><div class="l">{l}</div></div>' for v, l in stats)
    return f'''{title("02", "Executive architecture overview", "The short version", "Kota Aerospace is a working, well-tested modular monolith on a single PostgreSQL store. The software foundation is stronger than most platforms at this stage; the open work is at the edges — field connectivity, cross-path authorisation, decision lineage and production operations — not in the core.", "HYBRID", "hyb")}
<div class="cols c3" style="grid-template-columns:repeat(6,1fr);gap:3mm;margin-bottom:5mm">{st}</div>
<div class="cols c2" style="flex:1;gap:7mm">
 <div>
  <h3>What is verifiably true today</h3>
  <ul class="tight">
   <li><b>One deployable</b> FastAPI backend (57 routers, 523 handlers) + Next.js 16 frontend, three runtime processes: API, worker/scheduler, listeners.</li>
   <li><b>PostgreSQL is the only store of truth</b> — including telemetry, the job queue and an immutable audit log. No broker, no Neo4j, no TimescaleDB in use.</li>
   <li><b>Acquisition</b>: MAVLink v1/v2 (CRC, sequence, signing), MQTT, signed webhooks, OEM polling, CSV/JSON — all converge on one idempotent pipeline with quarantine.</li>
   <li><b>HUMS → M7 → LISA</b> chain is deterministic and grounded; RUL is labelled an estimate.</li>
   <li><b>Suite → plan → subscription</b> entitlements resolve per request in one resolver used by REST and LISA.</li>
   <li><b>Compliance</b>: three-valued applicability with configuration snapshots and reasoning traces.</li>
  </ul>
 </div>
 <div>
  <h3>What needs a decision or correction <span class="ref">→ {R("gaps")}</span></h3>
  <ul class="tight">
   <li><b>F1</b> ADR-003 still says Neo4j; the code chose PostgreSQL. Supersede it (ADR-011).</li>
   <li><b>F3</b> Workers, listeners and pollers do not re-check entitlements — a cancelled tenant keeps ingesting.</li>
   <li><b>F4</b> Edge store-and-forward is in memory and MAVLink is stamped with arrival time.</li>
   <li><b>F7</b> Signal vocabulary drift, including a live defect: overdue work orders in PLANNED / ASSIGNED / ON_HOLD / INSPECTION never raise M7 signals.</li>
   <li><b>F5 · F8</b> AI write boundary and compliance decision lineage are weaker than ADR-004/005 promise.</li>
   <li><b>Not started</b>: physical bench, pen test, restore drill, provider validation, customer UAT.</li>
  </ul>
  <div class="card amber" style="margin-top:3mm"><div class="quote">Recommendation: finish the foundations (acquisition, authorisation, lineage, operations) before adding agentic or predictive features.</div></div>
 </div>
</div>
<div class="cols c4" style="gap:4mm;margin-top:4mm">
 <div class="card blue"><div class="kicker">Runtime</div><p class="small">API · worker + scheduler · listeners — one image, three processes. <a class="ref" href="#d04">{R("d04")}</a></p></div>
 <div class="card cyan"><div class="kicker">Data</div><p class="small">PostgreSQL 16 for everything of record; S3-compatible files; derived views in SQL. <a class="ref" href="#data">{R("data")}</a></p></div>
 <div class="card amber"><div class="kicker">Intelligence</div><p class="small">Deterministic HUMS → M7 signals → grounded LISA; no learned models yet. <a class="ref" href="#d07">{R("d07")}</a></p></div>
 <div class="card acc"><div class="kicker">Governance</div><p class="small">Per-request RBAC + entitlements, immutable audit, retention by policy. <a class="ref" href="#d11">{R("d11")}</a></p></div>
</div>'''


# ====================================================================== audit
def p_audit():
    claims = [
        ("HUMS and telemetry foundations", "Code, migrations 0051–0058, 0070; tests", "VERIFIED"),
        ("M13 Phase 3 telemetry integration", "telemetry_service, acquisition pipeline, tests", "VERIFIED"),
        ("M7 proactive intelligence", "proactive_intelligence_service; lifecycle audited; one vocabulary defect", "PARTIAL"),
        ("M14 cross-asset intelligence", "Descriptive distributions only (H8.1 foundation)", "PARTIAL"),
        ("Grounded LISA tools", "61 tools, 257-case matrix; tool calls not persisted to audit", "PARTIAL"),
        ("Suite and subscription architecture", "Migrations 0059, 0061, 0064, 0069; resolver; tests", "VERIFIED"),
        ("Staging deployments", "Reports only (Vercel, Render, Neon); not inspected", "VERIFY"),
        ("Historical test baseline (2 690 passed)", "Re-run: 2 689 passed, 1 failed (start-up race), Python 3.12", "PARTIAL"),
        ("Neo4j derived graph (ADR-003, M14 report)", "Not used in code; PostgreSQL-only derived views", "SUPERSEDED"),
        ("Redis / TimescaleDB / Cloudflare topology", "Target text in deployment guide; not built", "DESIGNED"),
        ("ai_tool_audit_log (LISA doc)", "No such table or writer in code", "VERIFY"),
        ("RPO &lt; 15 min, RTO &lt; 1 h, WORM evidence", "Runbook targets; no drill or bucket policy in repo", "VERIFY"),
    ]
    rows = [[c, e, chip(s)] for c, e, s in claims]
    inspected = [("Backend", f"{REPO['py_files']} Python files · {REPO['api_routers']} routers · {REPO['models']} models · services, listeners, worker, scheduler"),
                 ("Database", f"{REPO['migrations']} Alembic migrations, upgraded on an empty PostgreSQL 16"),
                 ("Tests", f"{REPO['test_files']} backend test files re-run (pytest, Python 3.12); vitest re-run"),
                 ("Frontend", f"Next.js 16.3.5 · {REPO['frontend_pages']} pages · entitlement guard · mock-route redirects"),
                 ("Runtime & CI", "Dockerfile, docker-compose, GitHub Actions ci.yml, .vercel link"),
                 ("Documents", f"{REPO['adrs']} ADRs, ontology, ~120 milestone reports and architecture notes"),
                 ("Not reachable", "Staging / production hosts, provider consoles, physical devices")]
    return f'''{title("03", "Audit inventory &amp; evidence", "Phase 1 — what was inspected and what it proved", "Historical reports were treated as claims. Each claim was checked against code, migrations and a fresh test run; this page records the verdict.", "CURRENT VERIFIED", "cur")}
<div class="cols c31" style="flex:1">
 <div><h3>Historical claims → verdict</h3>{table(["Claim (from earlier reports)", "Evidence found in this audit", "Verdict"], rows, ["33%", "50%", "17%"])}</div>
 <div>
  <h3>Sources inspected</h3>{table(["Area", "Scope"], [[f"<b>{a}</b>", b] for a, b in inspected], ["28%", "72%"])}
  <div class="card coral" style="margin-top:4mm"><h3>Independent test run</h3>
   <p class="small"><b>{TESTRUN['passed']}</b> passed · <b>{TESTRUN['failed']}</b> failed · {TESTRUN['deselected']} deselected (real-storage) · {TESTRUN['seconds']} s on Python {TESTRUN['python']} + PostgreSQL 16.</p>
   <p class="small">Failed: <span class="mono">test_supervisor_starts_a_tcp_listener</span> — the test connects before the listener has bound its port (no readiness wait). Under Python 3.11 (the CI pin) one test file fails to collect.</p>
   <p class="small"><b>Frontend:</b> vitest {TESTRUN['vitest']} · tsc clean · ESLint {TESTRUN['eslint']}.</p></div>
 </div>
</div>'''


# ====================================================================== principles
def p_principles():
    P = [("Modular monolith by default", "VERIFIED", "One FastAPI deployable; boundaries by convention — import-linter not configured (F5)."),
         ("PostgreSQL authoritative", "VERIFIED", "All transactional, telemetry, audit and job data."),
         ("Neo4j as derived index", "SUPERSEDED", "Code uses PostgreSQL derived views; brief and ADR-003 need reconciling (F1)."),
         ("Domain ownership of logic, signals, evidence", "PARTIAL", "Clear in services; M7 vocabulary drift and two proactive surfaces (F7)."),
         ("Event-driven where valuable", "PARTIAL", "Durable job queue + audit log as event log; no versioned event contract (F2)."),
         ("Transactional outbox", "PARTIAL", "Jobs enqueued inside the request transaction = outbox-equivalent; not a formal outbox."),
         ("Grounded, permission-aware LISA", "VERIFIED", "Per-call authorisation; UNKNOWN when data absent; safety guard."),
         ("Suite-specific plans & subscriptions", "VERIFIED", "Plan belongs to one suite; one subscription per suite."),
         ("Tenant isolation & authZ in the backend", "PARTIAL", "Strong on HTTP; async ingestion paths skip entitlement (F3)."),
         ("Automated telemetry acquisition", "PARTIAL", "Software complete; field paths external; durable edge buffer missing (F4)."),
         ("Traceability observation → action", "PARTIAL", "IDs link packet to finding; signal ↔ work order via metadata only."),
         ("Human approval for regulated actions", "PARTIAL", "Release gates and RII are human; ADR-005 lineage not built (F8).")]
    rows = [[f"<b>{a}</b>", chip(s), c] for a, s, c in P]
    return f'''{title("04", "Product vision &amp; architectural principles", "Why the platform is shaped this way", "Kota connects physical aerospace assets, telemetry, health intelligence, maintenance and compliance through one grounded decision layer. The twelve principles below are the brief's own; each is scored against the code.")}
<div class="cols c21" style="flex:1">
 <div>{table(["Principle", "In code", "Evidence and gap"], rows, ["31%", "15%", "54%"])}</div>
 <div>
  <div class="card acc"><h3>Product scope</h3><p class="small">Drones and unmanned aircraft · conventional aircraft · helicopters · eVTOL · operators and fleets · MRO organisations · compliance and engineering teams.</p></div>
  <div class="card purple" style="margin-top:4mm"><h3>Complexity budget</h3><p class="small">No microservices, broker, graph database or additional agents unless a concrete requirement appears. The repository already proves the point: a PostgreSQL queue with SKIP LOCKED replaced a planned Redis broker, and SQL views replaced Neo4j.</p></div>
  <div class="card amber" style="margin-top:4mm"><h3>Non-negotiables</h3><ul class="tight"><li>No AI-made compliance or airworthiness determinations.</li><li>No data attached to an asset by guessing.</li><li>No estimate presented as a certified life limit.</li><li>No access decided by the frontend.</li></ul></div>
 </div>
</div>'''


# ====================================================================== D01
def p_d01():
    return f'''<h2 class="sr">05 Master ecosystem map — D01</h2>{fig(D.d01_master())}'''


def p_d01b():
    co = [(1, "", "Telemetry & acquisition", "listeners, webhooks, OEM pull, batch import; one idempotent pipeline.", "d05"),
          (2, "", "HUMS", "features, baselines, signatures, exceedances, RUL estimates.", "d06"),
          (3, "", "Signals & fleet intelligence", "M7 owns actionable signals; M14-ext describes; M4.2 presents.", "d07"),
          (4, "", "LISA", "61 tools, each authorised per call; refuses airworthiness determinations.", "d08"),
          (5, "", "MRO & inspections", "work orders, tasks, RII, parts, release-readiness gate.", "d10"),
          (6, "", "Compliance & evidence", "requirements, Kleene applicability, obligations, evidence review.", "d09"),
          (7, "", "Assets & operations", "registry for four families, configuration, missions, AOG.", "data"),
          (8, "cy", "Drone / UAV suite", "missions, batteries, MAVLink, HUMS starter sensors.", "suites"),
          (9, "cy", "Aircraft suite", "maintenance programme, AOG, compliance, release readiness.", "suites"),
          (10, "cy", "Helicopter suite", "rotor-system details, components; rotor analytics need OEM data.", "suites"),
          (11, "cy", "eVTOL / AAM suite", "propulsion / HV details, batteries; OEM models external.", "suites"),
          (12, "mi", "Platform ring", "identity, tenancy, entitlements, security, observability, admin.", "d12")]
    items = "".join(f'<div class="co"><div class="n {c}">{n}</div><div><b>{t}</b> — {s} <a class="ref" href="#{k}">{R(k)}</a></div></div>' for n, c, t, s, k in co)
    return f'''{title("05", "Master ecosystem map — guide", "D01 · Explanation", "The map is drawn as rings because every capability shares one core. Clockwise in the domain ring is the direction data normally travels: from telemetry through health intelligence and signals to people, work and compliance, and back into the asset record.", "HYBRID", "hyb")}
<div class="callouts" style="margin-bottom:5mm">{items}</div>
<div class="cols c3" style="flex:1">
 <div class="card acc"><h3>Dependencies that matter</h3><ul class="tight"><li>Every ring depends on the core store; nothing depends on the suites.</li><li>Suites are configuration (catalogue, plans, detail tables), not separate code bases.</li><li>LISA reads every domain but writes none (one exception, see D08).</li></ul></div>
 <div class="card amber"><h3>What the map does not claim</h3><ul class="tight"><li>Field devices, brokers, OEM clouds and model providers are drawn outside the boundary and are EXTERNAL.</li><li>The outcome-feedback loop is proposed.</li><li>Hosting is reported, not inspected (D04, D13).</li></ul></div>
 <div class="card blue"><h3>Interpretation</h3><p class="small">Read inside-out for ownership, clockwise for data, and outward for who is affected. Each numbered disc opens a detailed page.</p></div>
</div>'''


# ====================================================================== suites
def p_suites():
    rows = [["<b>Aircraft</b><br><span class='mono'>AIRCRAFT</span>", "Fleet, flights, maintenance programme, work orders, inspections, compliance, AOG, release readiness", "Aircraft detail tables; engines & components register", chip("VERIFIED"), "—"],
            ["<b>Drone / UAV</b><br><span class='mono'>DRONE_UAV</span>", "Fleet, missions, flights, batteries, telemetry, HUMS, M7, LISA", "MAVLink, MQTT, DJI webhook, OEM polling", chip("VERIFIED"), "Physical links EXTERNAL"],
            ["<b>Helicopter</b><br><span class='mono'>HELICOPTER</span>", "Rotor-system details, components (rotor / transmission / engine), hours & cycles, HUMS starter sensors, per-sensor limits", "airframe_details (0068), hums_templates", chip("VERIFIED"), "Track & balance, gearbox CI — OEM data"],
            ["<b>eVTOL / AAM</b><br><span class='mono'>EVTOL_AAM</span>", "Propulsion / HV details, batteries, components, hours & cycles, HUMS starter sensors", "same tables; voltage/current/temperature/vibration", chip("VERIFIED"), "Propulsor efficiency, thermal models — OEM data"]]
    return f'''{title("06", "Suite architecture", "Four suites, one platform", "A suite is a commercial and navigational boundary over shared modules — not a separate application. Suites, modules, pages and features are catalogue rows; a plan belongs to exactly one suite.", "CURRENT VERIFIED", "cur")}
{table(["Suite", "Capabilities", "Family-specific data", "Status", "External dependency"], rows, ["14%", "37%", "22%", "11%", "16%"])}
<div class="cols c3" style="margin-top:5mm;flex:1">
 <div class="card acc"><h3>Shared by every suite</h3><p class="small">Asset registry, telemetry pipeline, HUMS engines, M7, LISA, MRO, compliance, evidence, audit, identity and tenancy. The generic <span class="mono">/assets</span> endpoint checks the family's feature so it is not a side door (<span class="mono">_FAMILY_FEATURE</span>).</p></div>
 <div class="card amber"><h3>Suite boundary rules</h3><p class="small">Plan features outside the suite's domain are refused; tenant overrides cannot cross suites; subscriptions cannot move to another suite's plan. <b>Gap:</b> the domain rules live in code (<span class="mono">_SUITE_DISALLOWED_FEATURES</span>), so a new suite with a new domain needs a release.</p></div>
 <div class="card purple"><h3>Multi-suite organisations</h3><p class="small">One current subscription per suite; an organisation can hold several suites. LISA matches tools against the suites actually held (a defect locking multi-suite tenants out was fixed). See D11 <a class="ref" href="#d11">{R("d11")}</a>.</p></div>
</div>
<h3 style="margin-top:5mm">Adding a fifth suite — what is data and what is code</h3>
<div class="cols c4" style="gap:3mm">
 <div class="card cyan"><div class="kicker">1 · data</div><p class="small">Catalogue rows: suite, modules, pages, features (platform API). Frontend navigation follows automatically.</p></div>
 <div class="card cyan"><div class="kicker">2 · data</div><p class="small">Suite-specific plans with features and limits; subscriptions per organisation.</p></div>
 <div class="card amber"><div class="kicker">3 · code</div><p class="small">Domain boundary rule in <span class="mono">is_feature_allowed_for_suite</span>; router feature gates for any new family endpoints.</p></div>
 <div class="card amber"><div class="kicker">4 · code + migration</div><p class="small">Family detail table, HUMS starter template, UI pages, journey test — as done for helicopter / eVTOL in 0068.</p></div>
</div>'''


def p_d02():
    return f'''{ctitle("07", "Layered architecture", "D02 · Allowed and prohibited dependencies", "Seven stacked layers plus a cross-cutting governance column. Calls flow down only; governance applies to every layer.", "HYBRID", "hyb")}
{fig(D.d02_layers())}
{interp("Each chip's icon is its status. The red strip lists dependencies that must never appear in code review; the first two are enforced by design today (no DB credentials in the browser; LISA uses service functions), the last two by convention.", "module map " + R("d03") + " · boundaries " + R("deps"))}'''


def p_d03():
    return f'''{ctitle("08", "Backend modular monolith", "D03 · Eighteen modules in one deployable", "Modules are service packages inside one FastAPI application sharing one PostgreSQL schema. Arrows show the main runtime flows; full dependencies are in the matrix.", "CURRENT VERIFIED", "cur")}
{fig(D.d03_modules(), 25)}
{interp("Module ids (M01–M17, X01) are this blueprint's; mono text is the main source file. Note: ADR-001 names folders ai/, graph/, rules_engine/, document_intel/ — these exist but are empty; the code lives under services/.", "catalogue " + R("modcat") + " · ownership " + R("deps"))}'''


def _modrows(mods):
    return [[f"<b>{m['id']}</b>", f"<b>{m['name']}</b><br><span class='mono'>{m['area']}</span>", m["resp"], f"<span class='mono'>{m['entities']}</span>",
             f"<span class='mono'>{m['api']}</span>", m["emits"], m["deps"], chip(m["status"]) + (f"<br><span class='small' style='color:#5B6B7F'>{m['note']}</span>" if m["note"] else "")] for m in mods]


def p_modcat(part):
    mods = MODULES[(part - 1) * 6: part * 6]
    h = ["Id", "Module · owner area", "Responsibilities", "Main entities", "Public interface", "Events emitted", "Depends on", "Status"]
    return f'''{title("09", "Module catalogue" + (f" ({part}/3)"), "Ownership, interfaces and status", "Owner area is the accountable engineering area; data ownership means the module is the only writer of those tables. Events are AuditEvent actions or job types (see " + R("events") + ").", "CURRENT VERIFIED", "cur")}
<div style="flex:1;font-size:7.6pt">{table(h, _modrows(mods), ["4%", "12%", "24%", "17%", "12%", "11%", "9%", "11%"])}</div>'''


def p_deps():
    ids = ["M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "M10", "M11", "M12", "M13", "M14", "M16"]
    names = {m["id"]: m["name"].split(" (")[0].split(" &")[0] for m in MODULES}
    # R = reads/calls, W = writes through service, - none, X prohibited
    M = {
        "M04": {"M02": "R", "M03": "R"}, "M05": {"M04": "R", "M03": "R"},
        "M06": {"M04": "R", "M03": "G", "M07": "W", "M02": "R"}, "M07": {"M04": "R", "M06": "R", "M11": "W", "M13": "W"},
        "M08": {"M07": "R", "M10": "R", "M11": "R", "M12": "R", "M06": "R", "M04": "R"}, "M09": {"M08": "R", "M07": "R", "M04": "R"},
        "M10": {"M04": "R", "M11": "R", "M13": "W", "M03": "R"}, "M11": {"M04": "R", "M10": "R"}, "M12": {"M04": "R", "M13": "R", "M03": "R"},
        "M13": {"M04": "R"}, "M14": {"M04": "R", "M05": "R", "M06": "R", "M07": "R", "M08": "R", "M09": "R", "M10": "R", "M11": "R", "M12": "X", "M13": "R", "M03": "R"},
        "M03": {"M02": "R"}, "M02": {"M01": "R"}, "M01": {"M02": "R"}, "M16": {},
    }
    col = {"R": ("#E7F4F1", C["teal"]), "W": ("#FDF4E1", C["amberd"]), "X": ("#FDECE8", C["corald"]), "G": ("#FFF6E0", C["coral"])}
    head = "<tr><th></th>" + "".join(f'<th class="rot"><div>{i} {names[i][:16]}</div></th>' for i in ids) + "</tr>"
    body = ""
    for r in ids:
        body += f"<tr><td style='text-align:left;font-family:IBM Plex Sans Condensed;font-size:7.6pt;white-space:nowrap'><b>{r}</b> {names[r][:24]}</td>"
        for c in ids:
            v = M.get(r, {}).get(c, "")
            if r == c:
                body += '<td style="background:#0D2B49"></td>'
            elif v:
                bg, fg = col[v]
                lab = {"R": "read", "W": "write", "X": "✕", "G": "gap"}[v]
                body += f'<td style="background:{bg};color:{fg}">{lab}</td>'
            else:
                body += "<td></td>"
        body += "</tr>"
    return f'''{title("10", "Domain ownership &amp; dependency boundaries", "Who may call whom", "Rows depend on columns. ‘read’ = calls a read service; ‘write’ = invokes the owner's write service (never its tables); ✕ = prohibited; ‘gap’ = required check missing today.", "HYBRID", "hyb")}
<div class="cols c21" style="flex:1">
 <div class="heat"><table>{head}{body}</table></div>
 <div>
  <div class="card acc"><h3>Data ownership rules</h3><ul class="tight"><li>One writer per table: the owning module's service.</li><li>Cross-module writes go through the owner's service function inside the same transaction (e.g. HUMS → finding_service).</li><li>Derived modules (M09, LISA) own no facts.</li><li>Tenant id always from the caller or DataSource row.</li></ul></div>
  <div class="card coral" style="margin-top:4mm"><h3>Boundary findings</h3><ul class="tight"><li>M06 → M03: entitlement not re-checked on async paths (<b>gap</b>, F3).</li><li>M14 → M12: LISA may trigger a deterministic assessment (<span class="mono">run_assessment</span>) but must never write compliance results (✕).</li><li>No import-linter contracts; enforce with CI (F5).</li></ul></div>
 </div>
</div>'''


def p_d04():
    return f'''<h2 class="sr">11 Infrastructure topology — D04</h2>{fig(D.d04_infra())}
{interp("Zones are trust boundaries; dashed coral pills are failure and retry boundaries. Neo4j is drawn because docker-compose starts it — it is SUPERSEDED, not used. Hosting providers come from reports and are marked VERIFY.", "current vs target " + R("infra2") + " · security " + R("d12"))}'''


def p_infra2():
    rows = [("Web frontend", "Next.js 16 on Vercel (reported)", "Same; CDN caching for static assets", "VERIFY"),
            ("API service", "uvicorn, one image, $PORT; migrations as separate step", "≥2 instances behind TLS ingress; Gunicorn/uvicorn workers sized by test", "PARTIAL"),
            ("Worker & scheduler", "python -m app.worker --schedule; PostgreSQL queue", "Separate service; one scheduler leader; per-type concurrency", "VERIFIED"),
            ("Listeners", "python -m app.listeners (UDP/TCP/MQTT)", "Dedicated host / static IP per region; sequence state per source", "VERIFIED"),
            ("PostgreSQL", "Managed (Neon, reported); plain tables", "PITR verified by drill; partition telemetry by month when volume requires", "PARTIAL"),
            ("Cache / shared state", "Redis optional, for shared rate limits", "Required once API > 1 instance", "PARTIAL"),
            ("Object storage", "S3 API; MinIO locally", "Versioning + object lock (compliance mode) for evidence", "PARTIAL"),
            ("Message broker", "None — by design", "Only if fan-out / latency needs exceed the job queue (ADR-012)", "PROPOSED"),
            ("Graph store", "Neo4j container unused", "Remove; PostgreSQL derived views (ADR-011)", "SUPERSEDED"),
            ("Telemetry store", "hums_sensor_readings in PostgreSQL + retention", "Native partitioning first; TimescaleDB only on measured need", "PROPOSED"),
            ("Model gateway", "In-process provider abstraction (Anthropic / OpenAI-compatible)", "Per-tenant routing incl. no-external-AI mode for sovereign tenants", "PROPOSED"),
            ("Observability", "Prometheus-format endpoints, JSON logs, readiness", "Scrape + alert rules + dashboards + log shipping", "PARTIAL"),
            ("Backup & DR", "Provider snapshots (reported); runbook", "Quarterly restore drill with measured RPO/RTO", "VERIFY")]
    return f'''{title("12", "Current vs target infrastructure", "Comparison spread", "The target adds operations, not new architecture. Every row stays inside the modular-monolith, PostgreSQL-first decision.", "HYBRID", "hyb")}
{table(["Component", "Current (code + reports)", "Target (recommended)", "Status now"], [[f"<b>{a}</b>", b, c, chip(s)] for a, b, c, s in rows], ["17%", "36%", "34%", "13%"])}
<div class="cols c3" style="gap:4mm;margin-top:5mm">
 <div class="card blue"><h3>Why one database</h3><p class="small">Compliance answers years later need one transactional history. A second store of record would create the dual-write problem ADR-002 rules out.</p></div>
 <div class="card amber"><h3>When to add a store</h3><p class="small">Measured need only: telemetry partitioning first; a time-series engine if partitioned queries miss targets; a graph engine if traversal depth makes SQL the bottleneck.</p></div>
 <div class="card coral"><h3>Known data gaps</h3><p class="small">No partitioning on readings yet; MAVLink arrival-time stamping; signal ↔ work order link only in metadata; rule versions not stored.</p></div>
</div>'''


def p_data():
    stores = [("PostgreSQL 16", "All transactional data, telemetry readings, audit log, job queue", "Owning module per table", "Tenant FK on every row; append-only audit (trigger)"),
              ("Object storage", "Evidence files, exports, retention archives", "M13 Evidence", "SHA-256 checksum; sanitised keys; presigned 300 s"),
              ("Derived views", "Digital twin, knowledge graph, fleet distributions", "M09 (no ownership)", "Rebuilt per read; never a source of truth"),
              ("Process memory", "Rate-limit counters (default), MAVLink sequence state, edge buffer", "Runtime", "Lost on restart — documented trade-off")]
    contract = [("source_system / source_event_id", "idempotency key with organisation (unique)"), ("source_asset_id", "resolved via explicit mapping → id → unique serial/registration"),
                ("event_type · event_timestamp", "UTC; naive, >5 min future, pre-2000 rejected"), ("flight", "one Flight per streaming session, advisory-locked per asset"),
                ("battery", "updates an existing battery only; never invents cycles"), ("readings[]", "sensor_code, measurement_type, value (finite), unit, component_id, data_quality"),
                ("raw_metadata", "timestamp_source = SOURCE | RECEIVED")]
    ret = [("Telemetry readings", "policy-driven, dry-run default, archive-before-delete"), ("Evidence & audit", "kept (retention floor)"), ("Jobs", "succeeded jobs swept"), ("Destructive mode", "RETENTION_DESTRUCTIVE_ENABLED off by default")]
    return f'''{title("13", "Data architecture &amp; data contracts", "Stores, ownership and the canonical telemetry contract", "Kota keeps one database of record. Everything else is either a file referenced from it, a view derived from it, or process memory that may be lost.", "CURRENT VERIFIED", "cur")}
<div class="cols c2 fs72" style="flex:1">
 <div><h3>Stores</h3>{table(["Store", "Holds", "Owner", "Integrity"], [[f"<b>{a}</b>", b, c, d] for a, b, c, d in stores], ["17%", "33%", "20%", "30%"])}
  <h3 style="margin-top:4mm">Retention</h3>{table(["Data", "Rule"], [[f"<b>{a}</b>", b] for a, b in ret], ["35%", "65%"])}</div>
 <div><h3>Canonical contract — NormalizedTelemetryEvent</h3>{table(["Field", "Rule (enforced)"], [[f"<span class='mono'>{a}</span>", b] for a, b in contract], ["40%", "60%"])}
  <div class="card cyan" style="margin-top:4mm"><h3>Processing states</h3><p class="small"><span class="mono">RECEIVED → VALIDATED → PROCESSED</span>, or <span class="mono">DUPLICATE · REJECTED · QUARANTINED · FAILED</span>. Reading quality: VALID, SUSPECT, MISSING, OUT_OF_RANGE, STALE, DUPLICATE, INVALID.</p></div></div>
</div>
<div style="margin-top:0;width:94%;align-self:center">{D.x02_lineage().svg()}</div>'''


def p_d05():
    return f'''{ctitle("14", "Drone-to-cloud connectivity", "D05 · The most important field architecture problem", "Every path ends in the same validated, tenant-safe pipeline. What is not yet proven is the physical path from an airborne autopilot to that pipeline without a laptop.", "HYBRID", "hyb")}
{f'<div class="fig">{D.d05_connectivity().svg(crop=30, cropb=104)}</div>'}'''


def p_conn2():
    opts = [("Connected-aircraft service (OEM cloud)", "DJI Enterprise / OEM fleets with cloud telemetry", "Customer's OEM cloud tenancy + webhook secret or API credential", "Lowest effort; OEM data model limits signals", "VERIFIED / EXTERNAL"),
            ("Companion computer on aircraft", "PX4 / ArduPilot airframes Kota or the customer can modify", "Pi / Jetson, UART wiring, LTE modem, power, mounting, airworthiness of the modification", "Best data, live; hardware integration required", "PARTIAL / EXTERNAL"),
            ("Ground station / edge relay", "Radio-linked drones, no onboard modem", "GCS or relay host running mavlink-router with internet uplink", "Live within radio range; no airframe change", "EXTERNAL"),
            ("Automatic post-flight sync", "Any autopilot that writes logs", "Log parser (ULog / DataFlash) + sync agent on GCS or dock", "Not live; complete data; simplest field ops", "PROPOSED"),
            ("Manual import", "Fallback only", "Operator uploads CSV / JSON", "Human in the loop; not automation", "VERIFIED")]
    return f'''{title("15", "Connectivity options &amp; dependencies", "Decision guide for automated acquisition", "Choose per aircraft type. The software side is ready for all five; each row lists what must exist outside Kota.", "HYBRID", "hyb")}
{table(["Path", "Fits", "Needs (hardware / integration / external)", "Trade-off", "Status"], [[f"<b>{a}</b>", b, c, d, " ".join(chip(x.strip()) for x in e.split("/"))] for a, b, c, d, e in opts], ["19%", "19%", "27%", "20%", "15%"])}
<h3 style="margin-top:4mm">Decision tree — first supported path per aircraft type</h3>
<div>{D.x04_tree().svg()}</div>
<div class="cols c3" style="margin-top:3mm">
 <div class="card coral"><h3>Do not imply</h3><p class="small">Laptop-free live ingestion is not proven for any drone. It requires an onboard or ground relay that turns MAVLink serial into an authenticated network stream — a hardware integration, not a software setting.</p></div>
 <div class="card acc"><h3>Reliability mechanics (built)</h3><p class="small">Sequence per (sysid, compid); duplicates and late frames dropped; gaps counted as loss; DB uniqueness for idempotency; quarantine and replay; per-org back-pressure; source health from evidence.</p></div>
 <div class="card amber"><h3>To build (roadmap 1)</h3><p class="small">Disk-backed gateway queue · gateway sequence number · measurement time from SYSTEM_TIME / GPS with arrival time kept separately · per-device credentials · bench report on a real autopilot over UDP/TCP.</p></div>
</div>'''


def p_d06():
    return f'''{ctitle("16", "HUMS processing", "D06 · Health, usage, diagnostics, prognostics, RUL", "A deterministic chain from reading to evidence-backed finding. Predictive models are deliberately absent until outcome data exists.", "HYBRID", "hyb")}
{fig(D.d06_hums())}'''


def p_d07():
    return f'''{ctitle("17", "M7, M14-ext and M4.2 ownership", "D07 · One signal authority", "M7 owns actionable signals; M14-ext describes the fleet; M4.2 presents decisions; LISA explains. HUMS produces the evidence they all read.", "CURRENT VERIFIED", "cur")}
{fig(D.d07_ownership())}'''


def p_d08():
    return f'''<h2 class="sr">18 LISA and agentic AI — D08</h2>{fig(D.d08_lisa())}
{interp("Top row: request path. Middle: the authorisation chain shared with REST. Lower: tool classes and the governed-write tail. Proposed elements are what turns LISA from a grounded reader into a bounded agent.", "workflows " + R("agents") + " · entitlements " + R("d11"))}'''


def p_agents():
    W = [("Telemetry triage", "get_asset_telemetry_status · get_asset_proactive_signals · get_asset_hums_*", "Read", "None (explanation only)", "VERIFIED"),
         ("Maintenance planning", "signals + work orders + parts availability → draft work order with tasks and parts", "Draft", "Planner submits the draft; RII and release remain human", "PROPOSED"),
         ("Compliance evidence discovery", "obligations + evidence + requirements → missing-evidence list, draft checklist", "Read → draft", "Reviewer accepts evidence; LISA never marks compliant", "PARTIAL"),
         ("Fleet analysis", "fleet distributions, M7 summary, digital twin", "Read", "None", "VERIFIED"),
         ("Workflow coordination", "propose next steps across WO / procurement / inspections", "Draft", "Each state change confirmed by an authorised user", "PROPOSED")]
    return f'''{title("19", "Agentic workflows", "Bounded agents, not autonomous ones", "An agentic workflow here is a planned sequence of authorised tool calls that ends either in an answer or in a draft for a human. None ends in a regulated state change.", "HYBRID", "hyb")}
{table(["Workflow", "Tools / data", "Class", "Human gate", "Status"], [[f"<b>{a}</b>", b, c, d, chip(e)] for a, b, c, d, e in W], ["17%", "38%", "9%", "24%", "12%"])}
<div class="cols c3" style="margin-top:5mm;flex:1">
 <div class="card purple"><h3>Model routing &amp; grounding</h3><p class="small">One provider per deployment today (Anthropic or OpenAI-compatible; “not configured” otherwise). Proposed: per-tenant routing including a no-external-model mode for sovereign customers; answers must cite tool results; absence returns UNKNOWN.</p></div>
 <div class="card coral"><h3>Safety-critical boundary</h3><p class="small">Deterministic guard runs on the question, on tool results and on the final text: airworthiness, release-to-service, CRS, skip / bypass inspection phrasings are refused outside the model.</p></div>
 <div class="card amber"><h3>Before adding agents</h3><p class="small">Persist every tool call as an AuditEvent; classify tools; add a confirmation step for writes; build an evaluation set from real operator questions (roadmap 7). Do not add agents while F3 and F5 are open.</p></div>
</div>
<h3 style="margin-top:5mm">Bounded agent loop (target)</h3>
<div style="display:flex;gap:2mm;align-items:center;flex-wrap:nowrap"><div class="card purple" style="padding:2.4mm 3mm;flex:1"><div class="kicker" style="margin:0">1</div><div class="small" style="font-weight:600">Plan from intent</div></div><div style="color:#5B6B7F">→</div><div class="card acc" style="padding:2.4mm 3mm;flex:1"><div class="kicker" style="margin:0">2</div><div class="small" style="font-weight:600">Authorise each tool</div></div><div style="color:#5B6B7F">→</div><div class="card acc" style="padding:2.4mm 3mm;flex:1"><div class="kicker" style="margin:0">3</div><div class="small" style="font-weight:600">Run read tools</div></div><div style="color:#5B6B7F">→</div><div class="card coral" style="padding:2.4mm 3mm;flex:1"><div class="kicker" style="margin:0">4</div><div class="small" style="font-weight:600">Validate grounding</div></div><div style="color:#5B6B7F">→</div><div class="card amber" style="padding:2.4mm 3mm;flex:1"><div class="kicker" style="margin:0">5</div><div class="small" style="font-weight:600">Produce draft</div></div><div style="color:#5B6B7F">→</div><div class="card amber" style="padding:2.4mm 3mm;flex:1"><div class="kicker" style="margin:0">6</div><div class="small" style="font-weight:600">Human confirms</div></div><div style="color:#5B6B7F">→</div><div class="card blue" style="padding:2.4mm 3mm;flex:1"><div class="kicker" style="margin:0">7</div><div class="small" style="font-weight:600">Execute + audit</div></div></div>'''


def p_d09():
    return f'''{ctitle("20", "Compliance &amp; rules engine", "D09 · Source → interpretation → executable logic → output", "Source material, the engineer's interpretation, the executable rule and its evaluation are separate records, so each can be reviewed and revised without rewriting history.", "HYBRID", "hyb")}
{fig(D.d09_compliance())}'''


def p_d10():
    return f'''{ctitle("21", "MRO &amp; asset lifecycle", "D10 · From onboarding to the next due state", "HUMS findings, M7 signals and compliance obligations all inform maintenance, but only an authorised user creates or advances work.", "CURRENT VERIFIED", "cur")}
{fig(D.d10_mro())}'''


def p_d11():
    return f'''{ctitle("22", "Multi-tenancy, plans &amp; entitlements", "D11 · Commercial entitlement vs user authorisation", "Two independent questions — did the organisation buy it, and may this person do it — answered server-side on every request and combined into one decision.", "CURRENT VERIFIED", "cur")}
{fig(D.d11_entitlements())}'''


def p_d12():
    return f'''<h2 class="sr">23 Security and trust boundaries — D12</h2>{fig(D.d12_security())}
{interp("Nested zones are trust boundaries from least to most trusted; the controls that guard each boundary are written on it. Items to the right sit outside the runtime but inside the threat model.", "control register " + R("sec2"))}'''


def p_sec2():
    rows = [("Authentication", "JWT (exp + sub required), Argon2, DB re-check per request, SSO (OIDC/Entra)", "VERIFIED", "MFA policy at IdP; token revocation list"),
            ("Authorisation", "RBAC permissions + router-level entitlements + ownership checks", "PARTIAL", "Async paths (F3)"),
            ("Tenant isolation", "organization_id on every row; 404 for foreign ids; cross-tenant probe tests", "VERIFIED", "Optional PostgreSQL RLS as defence in depth"),
            ("Encryption", "TLS at edge (reported); at rest provider-managed (reported)", "VERIFY", "Document CMK / KMS per environment"),
            ("Secret management", "env KOTA_SECRET_<ref>; credentials refused in config JSON", "PARTIAL", "Vault / cloud secret manager + rotation"),
            ("Audit", "Immutable audit_events (trigger); lifecycle transitions audited", "VERIFIED", "LISA tool calls (F5)"),
            ("Data residency", "No region model in code", "PROPOSED", "Region per tenant; sovereign deployment profile"),
            ("Device credentials", "Edge device token hash, revoke; MAVLink-2 signing keys", "PARTIAL", "Per-device push credentials; rotation"),
            ("AI tool security", "Per-call authz, no org argument, safety guard, rate limit", "VERIFIED", "Tool classes; confirmation for writes"),
            ("Retention & evidence integrity", "Archive-before-delete; evidence checksums", "PARTIAL", "Object lock; periodic checksum verification")]
    return f'''{title("24", "Security controls &amp; sovereignty", "Control register", "No certification or defence-grade compliance is claimed. Controls below are those found in code; the right-hand column is the work needed before such a claim could be evaluated.", "HYBRID", "hyb")}
<div class="cols c31" style="flex:1">
 <div>{table(["Control", "Implemented", "Status", "Next step"], [[f"<b>{a}</b>", b, chip(c), d] for a, b, c, d in rows], ["17%", "45%", "12%", "26%"])}</div>
 <div>
  <div class="card purple"><h3>Sovereign deployment profile (ADR-016, proposed)</h3><p class="small">Same images, single-tenant stack in the customer's chosen region or private cloud; own database, storage and keys; model gateway set to an approved or on-premise provider or disabled; no shared observability backend.</p></div>
  <div class="card coral" style="margin-top:4mm"><h3>Open verification</h3><ul class="tight"><li>External penetration test</li><li>Dependency audit as a blocking CI gate</li><li>Infrastructure hardening review</li><li>DNS-rebinding residual risk on OEM polling — run workers with egress filtering</li></ul></div>
 </div>
</div>'''


def p_d13():
    return f'''{ctitle("25", "Deployment topology", "D13 · Environments and responsibilities", "Local and CI are verified from the repository. Staging and production hosting appear only in reports and were not inspected; the production topology is a recommendation.", "HYBRID", "hyb")}
{fig(D.d13_deploy())}
<div class="cols c3" style="margin-top:3mm">
 <div class="card acc"><h3>Release order</h3><p class="small">1 preflight SQL on a restore · 2 <span class="mono">alembic upgrade head</span> · 3 roll API, worker, listeners · 4 readiness reports schema head · 5 smoke tests.</p></div>
 <div class="card amber"><h3>Rollback</h3><p class="small">Roll the image back first; downgrade migrations only when safe — 0047 refuses to downgrade over existing non-task evidence rows by design.</p></div>
 <div class="card coral"><h3>Not done</h3><p class="small">Capacity test on production-like hardware, restore drill, on-call rota, alerting. This audit did not touch any hosted environment.</p></div>
</div>'''


def p_rel():
    rows = [("Database unavailable", "readiness 503; API errors; jobs wait", "Managed HA; alert on readiness", "VERIFIED"),
            ("Schema mismatch after deploy", "readiness 503 schema_mismatch", "Release order; drift guard test", "VERIFIED"),
            ("Worker crash mid-job", "job stays RUNNING → reclaimed after 10 min", "Visibility timeout; idempotent handlers", "VERIFIED"),
            ("Poison message", "retries with backoff → DEAD", "Dead-letter inspection + requeue", "VERIFIED"),
            ("Ingestion flood", "per-org queue cap 5 000 → drop + count", "Back-pressure metric alert", "VERIFIED"),
            ("Rate-limit backend down", "fail-closed for sensitive policies, local fallback otherwise", "Shared Redis HA", "VERIFIED"),
            ("Link loss in flight", "gateway buffers in memory; oldest dropped on overflow", "Disk queue (F4)", "PARTIAL"),
            ("Listener restart", "MAVLink sequence state forgotten", "One listener per source or persisted state", "PARTIAL"),
            ("LLM provider outage", "LISA reports not configured / error; domain unaffected", "Fallback provider", "VERIFIED"),
            ("Region loss", "—", "Backup restore in second region; drill", "VERIFY")]
    slo = [("API availability", "99.5 % monthly (proposed)"), ("Ingest-to-signal latency", "p95 &lt; 60 s for async path (proposed)"),
           ("Telemetry freshness", "stale source alert at 3× expected interval (built gauge)"), ("Dead jobs", "alert on any DEAD job (proposed)"), ("Restore", "RPO 15 min / RTO 1 h — targets until a drill measures them")]
    return f'''{title("26", "Reliability &amp; observability", "Failure modes and signals", "Most failure handling is already in code; what is missing is the operational loop that watches it.", "HYBRID", "hyb")}
<div class="cols c31" style="flex:1">
 <div>{table(["Failure", "Behaviour today", "Mitigation", "Status"], [[f"<b>{a}</b>", b, c, chip(d)] for a, b, c, d in rows], ["21%", "35%", "30%", "14%"])}</div>
 <div><h3>Service objectives (proposed)</h3>{table(["Objective", "Target"], [[f"<b>{a}</b>", b] for a, b in slo], ["45%", "55%"])}
  <div class="card cyan" style="margin-top:4mm"><h3>Signals already emitted</h3><p class="small">HTTP, auth and authorisation failures, rate limiting, ingest, packet loss, job outcomes, queue depth by status, data-source health, M7 signal events, HUMS evaluations, LISA tool latency and errors; JSON logs with request, tenant and correlation ids.</p></div></div>
</div>'''


def p_events():
    return f'''{ctitle("27", "Integration &amp; event architecture", "Events without a broker", "State change, its audit event and any follow-up job commit in one transaction. That gives outbox guarantees for jobs today; ADR-012 formalises versioning and consumer cursors.", "HYBRID", "hyb")}
{fig(D.x01_events())}
<div class="cols c3" style="margin-top:3mm">
 <div class="card acc"><h3>Queue semantics</h3><p class="small">At-least-once, effectively-once via idempotent handlers; unique (job_type, dedupe_key); exponential backoff with jitter; dead-letter; stale reclaim; correlation id carried into logs.</p></div>
 <div class="card amber"><h3>Versioning &amp; replay</h3><p class="small">No event_version today; consumers read action strings. Replay = re-query audit_events by time window. Proposed: version field, consumer cursor table, replay command.</p></div>
 <div class="card blue"><h3>External integration</h3><p class="small">Inbound: webhooks (HMAC), OEM pull, MQTT, MAVLink. Outbound: email only. Outbound webhooks or notifications should be driven from the same jobs table.</p></div>
</div>'''


def scen(n, key, d, mods, recs, evs, pol, fail):
    cells = [("Modules", mods), ("Records created", recs), ("Events emitted", evs), ("Policy checks", pol), ("Failure paths", fail)]
    strip = "".join(f'<div class="card" style="padding:2.6mm 3mm"><div class="kicker" style="margin-bottom:1mm">{a}</div><div class="small">{b}</div></div>' for a, b in cells)
    names = {1: ("Drone anomaly → reviewed maintenance", "A flight produces a vibration exceedance; HUMS evaluates it, M7 raises a signal, LISA explains it, and a person decides the maintenance action."),
             2: ("Compliance obligation → evidence → review", "A requirement applies to an aircraft; the rules engine decides applicability, finds missing evidence, and an authorised reviewer closes it."),
             3: ("Subscription → features → permissions", "An organisation subscribes to a suite plan; the resolver turns that into features and limits, combined with the user's permissions on every path.")}
    t, pur = names[n]
    return f'''{ctitle(str(27 + n), t, f"D14·{n} · end-to-end scenario", pur, "CURRENT VERIFIED" if n != 3 else "VERIFIED + GAP F3", "cur")}{fig(d)}<div class="cols" style="grid-template-columns:repeat(5,1fr);gap:3mm;margin-top:2mm">{strip}</div>'''


def p_s1():
    return scen(1, "s1", D.d14a_drone(), "M06 · M07 · M11 · M13 · M08 · M14 · M10 · X01",
                "telemetry_event_logs, hums_sensor_readings, flight, hums_feature, hums_exceedance, finding, evidence, proactive_signal_record, work_order",
                "acquisition.ingest job · finding.created · signal lifecycle audit · work_order.created",
                "source ACTIVE + signed · tenant from DataSource · RBAC + feature on LISA tool · permission on WO create",
                "drop unsigned · quarantine unknown asset · retry → dead-letter · LISA UNKNOWN if no data")


def p_s2():
    return scen(2, "s2", D.d14b_compliance(), "M12 · M04 · M13 · M08 · M16",
                "regulatory_requirement, applicability_rule + conditions, applicability_evaluation (snapshot, trace), compliance_obligation, evidence, evidence_file",
                "obligation sync audit · evidence lifecycle audit · COMPLIANCE_EVIDENCE_GAP signal",
                "compliance_management feature · REGULATION / ASSESSMENT permissions · reviewer ≠ uploader (recommended)",
                "UNKNOWN → review required · rejected evidence keeps obligation open · rule edit not versioned (F8)")


def p_s3():
    return scen(3, "s3", D.d14c_subscription(), "M17 · M03 · M02 · M01 · frontend · REST · LISA · X01",
                "plan + plan features, organization, subscription, users + roles, (optional) tenant overrides",
                "plan.* · subscription.* audit · billing.dunning job",
                "suite_plan_mismatch · one current subscription per suite · require_feature · RBAC · usage limits",
                "PAST_DUE grace → cancel (opt-in) · AMBIGUOUS → deny · async ingestion continues (F3)")


def p_status():
    caps = [("Identity, RBAC, SSO", "VERIFIED"), ("Tenancy & isolation (HTTP)", "VERIFIED"), ("Suite / plan / subscription", "VERIFIED"), ("Billing (test provider)", "PARTIAL"),
            ("Real payment provider", "EXTERNAL"), ("Asset registry, 4 families", "VERIFIED"), ("Missions, flights, AOG", "VERIFIED"), ("MAVLink codec + signing", "VERIFIED"),
            ("UDP/TCP/MQTT listeners", "VERIFIED"), ("Signed webhooks, OEM polling", "VERIFIED"), ("Serial MAVLink listener", "EXTERNAL"), ("Durable edge buffer", "PARTIAL"),
            ("Physical RF / autopilot validation", "EXTERNAL"), ("Post-flight log parsers", "PROPOSED"), ("HUMS deterministic chain", "VERIFIED"), ("Learned prognostics", "PROPOSED"),
            ("M7 signals + lifecycle", "PARTIAL"), ("M14-ext distributions", "VERIFIED"), ("M4.2 fleet summary", "VERIFIED"), ("Digital twin (SQL)", "VERIFIED"),
            ("Neo4j projection", "SUPERSEDED"), ("LISA tools + authz", "VERIFIED"), ("LISA tool audit persistence", "DESIGNED"), ("LISA governed writes", "PROPOSED"),
            ("Work orders, tasks, RII, release gate", "VERIFIED"), ("Parts, procurement, inventory", "VERIFIED"), ("Applicability engine", "VERIFIED"), ("Rule versioning", "PROPOSED"),
            ("ADR-005 decision lineage", "DESIGNED"), ("Evidence + checksums", "VERIFIED"), ("WORM evidence storage", "VERIFY"), ("Immutable audit log", "VERIFIED"),
            ("Job queue + scheduler", "VERIFIED"), ("Rate limiting (shared Redis)", "PARTIAL"), ("Metrics, logs, readiness", "VERIFIED"), ("Alerting / dashboards", "PROPOSED"),
            ("Retention", "VERIFIED"), ("Async entitlement re-check", "PARTIAL"), ("Notifications fan-out", "PROPOSED"), ("Staging hosting", "VERIFY"),
            ("Backup / restore drill", "VERIFY"), ("Penetration test", "EXTERNAL"), ("Customer UAT", "EXTERNAL"), ("10 sample-only pages", "PARTIAL")]
    counts = {}
    for _, s in caps:
        counts[s] = counts.get(s, 0) + 1
    cells = "".join(f'<div style="display:flex;justify-content:space-between;align-items:center;gap:2mm;padding:1.1mm 0;border-bottom:0.5pt solid {C["line"]};font-size:8.2pt;font-family:IBM Plex Sans Condensed"><span>{a}</span>{chip(s)}</div>' for a, s in caps)
    summ = "".join(f'<div class="stat" style="padding:2.4mm 3mm"><div class="v" style="font-size:17pt;color:{STATUS[k]["color"]}">{counts.get(k,0)}</div><div class="l">{chip(k)}</div></div>' for k in ["VERIFIED", "PARTIAL", "DESIGNED", "PROPOSED", "EXTERNAL", "VERIFY", "SUPERSEDED"])
    return f'''{title("31", "Implementation status register", "44 capabilities, one vocabulary", "Status as of commit 6bd38ce. ‘Software complete, gap count 0’ in the repository's own matrix is consistent with this register for software that can be tested locally; it does not cover the EXTERNAL, VERIFY or PROPOSED rows.", "CURRENT VERIFIED", "cur")}
<div class="cols" style="grid-template-columns:repeat(7,1fr);gap:3mm;margin-bottom:4mm">{summ}</div>
<div style="columns:3;column-gap:8mm;flex:1">{cells}</div>'''


def p_gaps(part=1):
    order = {"High": 0, "Medium": 1, "Low": 2}
    fs = sorted(FINDINGS, key=lambda f: (order[f["sev"]], int(f["id"][1:])))

    rows = [[f"<b>{f['id']}</b>", f'<span class="sev {f["sev"]}">{f["sev"].upper()}</span>', f"<b>{f['title']}</b><br><span class='small'>{f['body']}</span>", f["action"]] for f in fs]
    return f'''{ctitle("32", "Architecture gaps &amp; corrections", "Ten findings from the audit", "Ordered by severity. Each finding names the evidence; none required changing application code during this audit.", "CURRENT VERIFIED", "cur")}
<div class="fs72" style="flex:1">{table(["Id", "Severity", "Finding and evidence", "Correction"], rows, ["3%", "7%", "68%", "22%"])}</div>'''


def p_roadmap():
    rows = [[f"<b>{r['n']}</b>", f"<b>{r['title']}</b>", "<br>".join("· " + i for i in r["items"]), r["dep"], r["gate"]] for r in ROADMAP]
    return f'''{ctitle("33", "Recommended technical roadmap", "Dependency-aware, foundation first", "Advanced AI and prediction come last because they amplify whatever is underneath: if acquisition, permissions or lineage are unreliable, so are the answers.", "TARGET / PROPOSED", "tgt")}
{fig(D.x03_roadmap(), 0)}'''


def p_roadmap2():
    rows = [[f"<b>{r['n']}</b>", f"<b>{r['title']}</b>", "<br>".join("· " + i for i in r["items"]), r["dep"], r["gate"]] for r in ROADMAP]
    return f'''{title("33", "Roadmap — work items and exit gates", "Detail", "Each workstream closes on evidence, not on a date. Items reference the findings they resolve.", "TARGET / PROPOSED", "tgt")}
<div style="flex:1">{table(["#", "Workstream", "Work items", "After", "Exit gate (evidence)"], rows, ["4%", "22%", "44%", "7%", "23%"])}</div>'''


def p_adrs(part=1):
    sel = ADRS
    rows = [[f"<b>{a['id']}</b>", f"<b>{a['title']}</b><br><span class='mono'>{a['status']}</span>", a["problem"], a["choice"], a["alts"], a["trade"], a["risk"], a["validate"], chip(a["impl"])] for a in sel]
    return f'''{title("34", "Architecture decision register", "Ten recorded decisions, checked against code", "Decision status is the ADR's own; implementation is this audit's verdict. ADR-003 is the one decision the code has overturned.", "CURRENT VERIFIED", "cur")}
<div class="fs72" style="flex:1">{table(["ADR", "Decision · status", "Problem", "Approach", "Alternatives", "Trade-offs", "Risk observed", "Validation needed", "In code"], rows, ["6%", "12%", "12%", "13%", "10%", "9%", "16%", "12%", "10%"])}</div>'''


def p_approve():
    rows = [[f"<b>{p['id']}</b>", f"<b>{p['title']}</b>", p["why"], p["reverse"], chip("PROPOSED")] for p in PROPOSED_DECISIONS]
    tr = [("Modular monolith vs microservices", "Keep the monolith. Split candidates, in order, only on evidence: listeners (network exposure), worker (scaling), LISA (provider isolation)."),
          ("PostgreSQL vs specialised stores", "Partition telemetry before adopting TimescaleDB; object storage for files; no second database of record."),
          ("Telemetry storage & retention", "Raw readings retained per policy; features and exceedances kept; evidence never deleted."),
          ("Multi-tenant isolation", "Shared schema with tenant FK now; RLS as defence in depth; dedicated stacks for sovereign tenants.")]
    q = ["Does the brief's ‘Neo4j as derived index’ principle stand, or is ADR-011 (PostgreSQL) accepted?",
         "Which connectivity path (D05 A–E) is the first supported production path, and on which airframe?",
         "Build or retire the 10 sample-only pages (/finance, /reports, /workspace …)?",
         "Is a sovereign / defence deployment a 2027 requirement? It changes model routing and hosting.",
         "Who owns this blueprint and approves ADR changes?"]
    return f'''{title("35", "Decisions &amp; trade-offs requiring approval", "For the product and engineering owners", "Six proposed decisions and five open questions. None is implemented; each lists the evidence that would reverse it.", "TARGET / PROPOSED", "tgt")}
{table(["Id", "Proposed decision", "Why it fits", "Reverse if", "Status"], rows, ["7%", "25%", "41%", "17%", "10%"])}
<div class="cols c2" style="margin-top:4mm;flex:1">
 <div class="card blue"><h3>Key trade-offs</h3>{"".join(f"<p class='small'><b>{a}.</b> {b}</p>" for a, b in tr)}</div>
 <div class="card amber"><h3>Questions only you can answer</h3><ol class="tight" style="padding-left:5mm;margin:0;font-size:8.8pt;line-height:1.5">{"".join(f"<li>{x}</li>" for x in q)}</ol></div>
</div>'''


def p_gloss():
    half = (len(GLOSSARY) + 1) // 2
    g1 = table(["Term", "Meaning"], [[f"<b>{a}</b>", b] for a, b in GLOSSARY[:half]], ["22%", "78%"])
    g2 = table(["Term", "Meaning"], [[f"<b>{a}</b>", b] for a, b in GLOSSARY[half:]], ["22%", "78%"])
    ch = table(["Version", "Date", "Change"], [["v1.0", "2026-10-01", "First edition: audit of commit 6bd38ce, 14 diagram families, status register, 10 findings, roadmap, decision register."]], ["14%", "20%", "66%"])
    return f'''{title("36", "Glossary, diagram legend &amp; change history", "Reference", "Acronyms are expanded here once; the legend is on page " + R("legend:n") + ".")}
<div class="cols" style="grid-template-columns:1fr 1fr 0.9fr;gap:6mm;flex:1">
 <div>{g1}</div><div>{g2}</div>
 <div><h3>Change history</h3>{ch}
  <h3 style="margin-top:5mm">Diagram index</h3>
  <p class="small">D01 master ecosystem · D02 layers · D03 modules · D04 infrastructure · D05 connectivity · D06 HUMS · D07 intelligence ownership · D08 LISA · D09 compliance · D10 MRO · D11 entitlements · D12 security · D13 deployment · D14·1–3 scenarios · X01 events · X02 lineage · X03 roadmap.</p>
  <h3 style="margin-top:5mm">Editable sources</h3>
  <p class="small"><span class="mono">src/diagrams.py</span> (all diagrams, Python → SVG) · <span class="mono">src/model.py</span> (modules, findings, ADRs, roadmap) · <span class="mono">svg/*.svg</span> · <span class="mono">mermaid/*.mmd</span> · <span class="mono">ARCHITECTURE_SOURCE_OF_TRUTH.md</span>.</p></div>
</div>'''


# order: (key, section label, builder, dark)
PAGES = [
    ("cover", None, p_cover, True),
    ("toc", ("", "CONTENTS"), p_toc, False),
    ("legend", ("01", "READING GUIDE"), p_legend, False),
    ("exec", ("02", "EXECUTIVE OVERVIEW"), p_exec, False),
    ("audit", ("03", "AUDIT INVENTORY"), p_audit, False),
    ("principles", ("04", "VISION & PRINCIPLES"), p_principles, False),
    ("d01", ("05", "MASTER ECOSYSTEM MAP"), p_d01, True),
    ("d01b", ("05", "MASTER ECOSYSTEM MAP"), p_d01b, False),
    ("suites", ("06", "SUITE ARCHITECTURE"), p_suites, False),
    ("d02", ("07", "LAYERED ARCHITECTURE"), p_d02, False),
    ("d03", ("08", "BACKEND MODULAR MONOLITH"), p_d03, False),
    ("modcat", ("09", "MODULE CATALOGUE"), lambda: p_modcat(1), False),
    ("modcat2", ("09", "MODULE CATALOGUE"), lambda: p_modcat(2), False),
    ("modcat3", ("09", "MODULE CATALOGUE"), lambda: p_modcat(3), False),
    ("deps", ("10", "OWNERSHIP & BOUNDARIES"), p_deps, False),
    ("d04", ("11", "INFRASTRUCTURE TOPOLOGY"), p_d04, True),
    ("infra2", ("12", "CURRENT VS TARGET"), p_infra2, False),
    ("data", ("13", "DATA ARCHITECTURE"), p_data, False),
    ("d05", ("14", "TELEMETRY & CONNECTIVITY"), p_d05, False),
    ("conn2", ("15", "CONNECTIVITY OPTIONS"), p_conn2, False),
    ("d06", ("16", "HUMS PROCESSING"), p_d06, False),
    ("d07", ("17", "INTELLIGENCE OWNERSHIP"), p_d07, False),
    ("d08", ("18", "LISA & AGENTIC AI"), p_d08, True),
    ("agents", ("19", "AGENTIC WORKFLOWS"), p_agents, False),
    ("d09", ("20", "COMPLIANCE & RULES"), p_d09, False),
    ("d10", ("21", "MRO & LIFECYCLE"), p_d10, False),
    ("d11", ("22", "PLANS & ENTITLEMENTS"), p_d11, False),
    ("d12", ("23", "SECURITY & TRUST"), p_d12, True),
    ("sec2", ("24", "SECURITY CONTROLS"), p_sec2, False),
    ("d13", ("25", "DEPLOYMENT"), p_d13, False),
    ("rel", ("26", "RELIABILITY & OBSERVABILITY"), p_rel, False),
    ("events", ("27", "INTEGRATION & EVENTS"), p_events, False),
    ("s1", ("28", "SCENARIO 1"), p_s1, False),
    ("s2", ("29", "SCENARIO 2"), p_s2, False),
    ("s3", ("30", "SCENARIO 3"), p_s3, False),
    ("status", ("31", "IMPLEMENTATION STATUS"), p_status, False),
    ("gaps", ("32", "GAPS & CORRECTIONS"), p_gaps, False),
    ("roadmap", ("33", "ROADMAP"), p_roadmap, False),
    ("roadmap2", ("33", "ROADMAP"), p_roadmap2, False),
    ("adrs", ("34", "DECISION REGISTER"), p_adrs, False),
    ("approve", ("35", "APPROVALS"), p_approve, False),
    ("gloss", ("36", "GLOSSARY & LEGEND"), p_gloss, False),
]
