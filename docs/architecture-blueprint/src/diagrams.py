"""All Kota blueprint diagrams. Each function returns a svg.Diagram.

Naming: d01_* … d14_* follow the mandatory diagram numbering in the brief; x* are supporting diagrams.
"""
from __future__ import annotations

import math

from svg import ARROW, C, KIND, STATUS, Diagram, esc, text_width, wrap


# ------------------------------------------------------------------ geometry helpers
def P(cx, cy, r, a):
    t = math.radians(a)
    return cx + r * math.sin(t), cy - r * math.cos(t)


def sector(cx, cy, r1, r2, a0, a1):
    large = 1 if (a1 - a0) > 180 else 0
    x0, y0 = P(cx, cy, r2, a0)
    x1, y1 = P(cx, cy, r2, a1)
    x2, y2 = P(cx, cy, r1, a1)
    x3, y3 = P(cx, cy, r1, a0)
    return (f"M{x0:.1f},{y0:.1f} A{r2},{r2} 0 {large} 1 {x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f} "
            f"A{r1},{r1} 0 {large} 0 {x3:.1f},{y3:.1f} Z")


def arcpath(cx, cy, r, a0, a1):
    """Path along an arc, oriented so text reads upright."""
    mid = ((a0 + a1) / 2) % 360
    if 90 < mid < 270:  # bottom half: draw counter-clockwise
        x0, y0 = P(cx, cy, r, a1)
        x1, y1 = P(cx, cy, r, a0)
        sweep = 0
    else:
        x0, y0 = P(cx, cy, r, a0)
        x1, y1 = P(cx, cy, r, a1)
        sweep = 1
    large = 1 if (a1 - a0) > 180 else 0
    return f"M{x0:.1f},{y0:.1f} A{r},{r} 0 {large} {sweep} {x1:.1f},{y1:.1f}"


def arc_text(d: Diagram, pid, cx, cy, r, a0, a1, s, size=10, color="#fff", weight=500, face="'IBM Plex Mono'", ls=1.4):
    mid = ((a0 + a1) / 2) % 360
    rr = r - size * 0.32 if not (90 < mid < 270) else r + size * 0.32 + 1
    d.raw(f'<path id="{pid}" d="{arcpath(cx, cy, rr, a0, a1)}" fill="none"/>')
    d.raw(f'<text font-family="{face}" font-size="{size}" font-weight="{weight}" fill="{color}" letter-spacing="{ls}">'
          f'<textPath href="#{pid}" startOffset="50%" text-anchor="middle">{esc(s)}</textPath></text>')


# ================================================================== D1 master ecosystem
def d01_master():
    d = Diagram(1040, 660, dark=True, title="D01 Master ecosystem architecture")
    cx, cy = 520, 336
    # outer halo
    d.circle(cx, cy, 300, fill="none", stroke="#1E4468", sw=0.8, dash="2 5")
    # platform ring (cross-cutting)
    plat = [("IDENTITY · RBAC · SSO", "VERIFIED"), ("TENANCY", "VERIFIED"), ("ENTITLEMENTS · BILLING", "VERIFIED"),
            ("SECURITY · RATE LIMITS", "VERIFIED"), ("OBSERVABILITY", "VERIFIED"), ("PLATFORM ADMIN · AUDIT", "VERIFIED")]
    for i, (lab, st) in enumerate(plat):
        a0, a1 = i * 60 + 1, (i + 1) * 60 - 1
        d.raw(f'<path d="{sector(cx, cy, 246, 272, a0, a1)}" fill="#0F2F4D" stroke="{C["mint"]}" stroke-width="0.8" opacity="0.95"/>')
        arc_text(d, f"pl{i}", cx, cy, 259, a0, a1, lab, 8.6, C["mint"], 500)
    # suites ring
    suites = [("DRONE / UAV SUITE", C["cyan"]), ("AIRCRAFT SUITE", C["blue"]), ("HELICOPTER SUITE", "#5AA0E6"), ("eVTOL / AAM SUITE", C["mint"])]
    for i, (lab, col) in enumerate(suites):
        a0, a1 = i * 90 - 44, i * 90 + 44
        d.raw(f'<path d="{sector(cx, cy, 194, 240, a0, a1)}" fill="#123A60" stroke="{col}" stroke-width="1.2"/>')
        arc_text(d, f"su{i}", cx, cy, 217, a0, a1, lab, 10.5, C["white"], 600, "'IBM Plex Sans Condensed'", 1.6)
    # domain ring
    dom = [("Telemetry & acquisition", "M06 · listeners, webhooks, OEM pull", C["cyan"], "data"),
           ("HUMS", "M07 · features → RUL", C["teal"], "domain"),
           ("Signals & fleet intelligence", "M7 · M14-ext · M4.2", C["amber"], "decision"),
           ("LISA", "61 governed tools", C["purple"], "ai"),
           ("MRO & inspections", "work orders → release", C["teal"], "domain"),
           ("Compliance & evidence", "rules · obligations", C["amber"], "decision"),
           ("Assets & operations", "registry · missions · AOG", C["blue"], "infra")]
    n = len(dom)
    step = 360 / n
    for i, (t, s, col, k) in enumerate(dom):
        a0, a1 = i * step - step / 2 + 0.8, i * step + step / 2 - 0.8
        d.raw(f'<path d="{sector(cx, cy, 94, 186, a0, a1)}" fill="{KIND[k][2]}" stroke="{col}" stroke-width="1.3"/>')
        mx, my = P(cx, cy, 142, i * step)
        lines = wrap(t, 92, 11.5, "cond", 600)
        y0 = my - (len(lines) * 13 + 11) / 2 + 10
        for j, ln in enumerate(lines):
            d.text(mx, y0 + j * 13, ln, 11.5, 600, C["white"], "middle")
        for j, ln in enumerate(wrap(s, 84, 7.8, "mono")):
            d.text(mx, y0 + len(lines) * 13 + 1 + j * 10, ln, 7.8, 400, "#A9BDD3", "middle", "mono")
    # clockwise data-flow chevrons between domain sectors
    for i in range(n):
        a = i * step + step / 2
        x, y = P(cx, cy, 190, a)
        d.circle(x, y, 2.4, fill=C["cyan"])
    # core
    d.circle(cx, cy, 88, fill="#0A2440", stroke=C["cyan"], sw=1.6)
    d.circle(cx, cy, 80, fill="none", stroke="#2A5A86", sw=0.6, dash="2 3")
    d.text(cx, cy - 40, "KOTA CORE", 9, 500, C["cyan"], "middle", "mono", ls=2.2)
    d.text(cx, cy - 18, "PostgreSQL 16", 15, 700, C["white"], "middle", "disp")
    d.text(cx, cy - 4, "system of record", 9.5, 400, "#A9BDD3", "middle")
    d.line(cx - 50, cy + 6, cx + 50, cy + 6, "#2A5A86", 0.8)
    for j, ln in enumerate(["audit log = event log", "durable job queue", "entitlement resolver", "derived graph (in SQL)"]):
        d.text(cx, cy + 21 + j * 12.5, ln, 9.2, 500, "#D8E4F0", "middle")
    # left: people & orgs
    d.zone(20, 70, 196, 470, "Customers & users", "user", fill="#0A2238")
    people = [("Fleet operators", "drone · aircraft · rotorcraft · eVTOL"), ("MRO organisations", "Part-145 style shops"),
              ("Compliance & engineering", "CAMO, quality, airworthiness"), ("Platform administrators", "Kota control plane")]
    for i, (t, s) in enumerate(people):
        d.box(34, 92 + i * 76, 168, 62, t, s, "user", tsize=12)
    d.box(34, 404, 168, 120, "Web application", "Next.js 16 · 137 pages · entitlement-aware navigation", "infra", "VERIFIED",
          note="Display only — every control is enforced by the backend.")
    # right: field and external
    d.zone(824, 70, 196, 470, "Field & external systems", "ext", fill="#0A2238")
    ext = [("Drones & autopilots", "MAVLink v1/v2 · PX4 / ArduPilot", "EXTERNAL"), ("Edge gateways · GCS relays", "store-and-forward", "PARTIAL"),
           ("MQTT brokers · OEM clouds", "DJI FlightHub · OEM REST", "EXTERNAL"), ("LLM provider", "Anthropic / OpenAI-compatible", "EXTERNAL"),
           ("Email · payments", "SMTP · billing provider", "EXTERNAL")]
    for i, (t, s, st) in enumerate(ext):
        d.box(838, 92 + i * 88, 168, 74, t, s, "ext", st, tsize=12)
    # arrows into the rings
    d.arrow([(202, 464), (262, 464), (300, 420)], "sync", "HTTPS · JWT")
    d.arrow([(838, 129), (776, 129), (740, 168)], "async", "telemetry", lseg=0)
    d.arrow([(838, 217), (790, 217), (762, 240)], "async")
    d.arrow([(838, 305), (800, 305)], "async", "push / poll", lseg=0)
    d.arrow([(756, 405), (838, 405)], "sync", "model calls", lseg=0)
    d.arrow([(756, 487), (838, 487)], "sync", "notify · bill", lseg=0)
    # feedback loop label
    d.arrow([(640, 612), (520, 628), (400, 612)], "proposed", "outcome feedback → baselines (proposed)", lpos=(520, 628))
    # callouts
    calls = [(1, 0), (2, 1), (3, 2), (4, 3), (5, 4), (6, 5), (7, 6)]
    for k, i in calls:
        x, y = P(cx, cy, 176, i * step - step / 2 + 9)
        d.num(x, y, k, 9)
    for k, a in [(8, -44 + 8), (9, 46 + 8), (10, 136 + 8), (11, 226 + 8)]:
        x, y = P(cx, cy, 231, a)
        d.num(x, y, k, 9, C["cyan"])
    x, y = P(cx, cy, 259, 180)
    d.num(x, y, 12, 9, C["mint"])
    # header strip
    d.text(20, 30, "D01", 11, 600, C["amber"], face="mono", ls=1.5)
    d.text(52, 30, "MASTER ECOSYSTEM ARCHITECTURE", 11, 600, C["white"], face="mono", ls=1.5)
    d.badge(1020, 19, "VERIFIED", "end", 8.5)
    d.text(916, 30, "HYBRID VIEW", 9, 500, "#A9BDD3", "end", "mono", ls=1.2)
    d.text(20, 650, "Rings, inside out: core store → shared domain capabilities (clockwise = direction of data) → four product suites → cross-cutting platform services.",
           9.2, 400, "#A9BDD3")
    return d


# ================================================================== D2 layered architecture
def d02_layers():
    d = Diagram(1040, 612, title="D02 Layered architecture")
    layers = [
        ("1", "User experience", "user", [("Web application", "Next.js 16 · React", "VERIFIED"), ("LISA assistant panel", "/ai", "VERIFIED"),
                                            ("Platform console", "/platform", "VERIFIED"), ("Demo mode", "sample data, labelled", "PARTIAL")]),
        ("2", "Presentation & API edge", "infra", [("57 FastAPI routers", "523 handlers", "VERIFIED"), ("AuthN + RBAC deps", "core/deps.py", "VERIFIED"),
                                                     ("Entitlement gates", "require_feature", "VERIFIED"), ("Rate limiting", "policy middleware", "VERIFIED"),
                                                     ("Ingest & webhooks", "HMAC · replay guard", "VERIFIED")]),
        ("3", "Application & orchestration", "ai", [("Domain services", "services/*", "VERIFIED"), ("LISA orchestration", "services/lisa · ai", "VERIFIED"),
                                                      ("Acquisition orchestrator", "acquisition_service", "VERIFIED"), ("Job handlers · scheduler", "worker.py", "VERIFIED"),
                                                      ("Provisioning factory", "provisioning_service", "VERIFIED")]),
        ("4", "Domain modules", "domain", [("Assets · fleet ops", "M04 · M05", "VERIFIED"), ("Telemetry · HUMS", "M06 · M07", "VERIFIED"),
                                             ("M7 signals", "M08", "VERIFIED"), ("MRO · inspections", "M10 · M11", "VERIFIED"),
                                             ("Compliance · evidence", "M12 · M13", "PARTIAL")]),
        ("5", "Persistence & transactional events", "data", [("PostgreSQL 16", "95 tables · Alembic 0070", "VERIFIED"), ("audit_events", "append-only trigger", "VERIFIED"),
                                                              ("background_jobs", "SKIP LOCKED queue", "VERIFIED"), ("Transactional outbox", "named pattern", "DESIGNED")]),
        ("6", "Derived analytics & search", "decision", [("Digital twin / graph", "derived, in SQL", "VERIFIED"), ("Fleet distributions", "M14-ext · M4.2", "VERIFIED"),
                                                           ("Neo4j projection", "ADR-003", "SUPERSEDED"), ("Search index", "not built", "PROPOSED")]),
        ("7", "Infrastructure & external", "ext", [("Object storage", "S3 / MinIO", "VERIFIED"), ("Redis", "shared rate limit", "PARTIAL"),
                                                    ("LLM provider", "configurable", "EXTERNAL"), ("Field sources", "radios · brokers · OEM", "EXTERNAL"),
                                                    ("Email · payments", "providers", "EXTERNAL")]),
    ]
    x0, lw, top, lh, gap = 52, 168, 34, 64, 9
    cx0, cx1 = x0 + lw + 10, 812
    for i, (n, name, kind, chips) in enumerate(layers):
        y = top + i * (lh + gap)
        acc = KIND[kind][0]
        d.rect(x0, y, cx1 - x0 + 8, lh, fill=KIND[kind][1], stroke="none", rx=8)
        d.rect(x0, y, lw, lh, fill=acc, rx=8)
        d.text(x0 + 14, y + 26, n, 20, 700, C["white"], face="disp")
        d.mtext(x0 + 40, y + 24, name, lw - 50, 12, 600, C["white"])
        k = len(chips)
        cw = (cx1 - cx0 - (k - 1) * 8) / k
        for j, (t, s, st) in enumerate(chips):
            d.chip(cx0 + j * (cw + 8), y + 9, cw, lh - 18, t, s, kind, st)
    # governance column (layer 8)
    gx = 838
    gy1 = top + 7 * (lh + gap) - gap
    d.rect(gx, top, 186, gy1 - top, fill=KIND["gov"][1], stroke=C["mint"], rx=10)
    d.rect(gx, top, 186, 50, fill=C["teal"], rx=10)
    d.text(gx + 14, top + 31, "8", 20, 700, C["white"], face="disp")
    d.mtext(gx + 38, top + 21, "Cross-cutting governance", 140, 12, 600, C["white"])
    gov = [("Tenant isolation", "organization_id on every row", "VERIFIED"), ("RBAC permissions", "server-side, DB roles", "VERIFIED"),
           ("Commercial entitlements", "one resolver", "PARTIAL"), ("Immutable audit", "DB trigger", "VERIFIED"),
           ("Observability", "logs · metrics · health", "VERIFIED"), ("Retention", "dry-run default", "VERIFIED"),
           ("Secrets", "env KOTA_SECRET_*", "PARTIAL")]
    for j, (t, s, st) in enumerate(gov):
        d.chip(gx + 10, top + 62 + j * 64, 166, 54, t, s, "gov", st)
    # allowed dependency spine (left gutter)
    for i in range(6):
        y = top + i * (lh + gap) + lh - 6
        d.arrow([(26, y), (26, y + gap + 12)], "sync")
    d.raw(f'<text transform="translate(16,{top + 3.5*(lh+gap)}) rotate(-90)" font-family="\'IBM Plex Mono\'" font-size="7.8" '
          f'fill="{C["slate"]}" text-anchor="middle" letter-spacing="1">ALLOWED: CALLS FLOW DOWN</text>')
    # governance tie lines
    for i in range(7):
        y = top + i * (lh + gap) + lh / 2
        d.line(cx1 + 8, y, gx, y, C["mint"], 1, "2 3")
    # prohibited dependencies (strip below the stack)
    py = top + 7 * (lh + gap) + 12
    d.rect(x0, py, 1024 - x0, 50, fill="#FDECE8", stroke=C["coral"], rx=8, dash="4 3")
    d.text(x0 + 14, py + 20, "PROHIBITED", 8.5, 600, C["corald"], face="mono", ls=1.4)
    d.text(x0 + 14, py + 36, "never allowed", 9, 400, C["corald"])
    items = ["UI or LISA reads/writes the database directly", "Upward call (domain → API layer)",
             "AI tool writes compliance results", "Derived view treated as source of truth"]
    iw = (1024 - x0 - 120) / 4
    for k, t in enumerate(items):
        ix = x0 + 112 + k * iw
        d.arrow([(ix, py + 25), (ix + 26, py + 25)], "prohibited")
        d.mtext(ix + 34, py + 21, t, iw - 44, 9.6, 500, C["ink"], lh=1.2)
    d.text(52, 20, "D02 · LAYERED ARCHITECTURE", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1024, 20, "HYBRID — VERIFIED + PROPOSED DISTINGUISHED", 9, 500, C["slate"], "end", "mono", ls=1.2)
    return d


# ================================================================== D3 backend module map
def d03_modules():
    from model import MODULES
    m = {x["id"]: x for x in MODULES}
    d = Diagram(1040, 590, title="D03 Backend modular monolith")
    cw, ch, gx, gy, x0, y0 = 186, 104, 18, 34, 20, 44
    pos = {"M01": (0, 0), "M02": (1, 0), "M15": (2, 0), "M03": (3, 0), "M17": (4, 0),
           "M04": (0, 1), "M05": (1, 1), "M06": (2, 1), "X01": (3, 1), "M16": (4, 1),
           "M07": (0, 2), "M08": (1, 2), "M09": (2, 2), "M14": (3, 2),
           "M10": (0, 3), "M11": (1, 3), "M12": (2, 3), "M13": (3, 3)}
    kinds = {"Platform core": "infra", "Commercial": "gov", "Governance": "gov", "Shared domain": "infra", "Data acquisition": "data",
             "Runtime": "data", "Intelligence": "decision", "Operations": "domain", "Compliance": "decision"}

    def xy(c, r):
        return x0 + c * (cw + gx), y0 + r * (ch + gy)
    zones = [("Platform core", 0, 0, 3, 1, "infra"), ("Commercial", 3, 0, 1, 1, "gov"), ("Governance", 4, 0, 1, 2, "gov"),
             ("Shared domain", 0, 1, 2, 1, "infra"), ("Acquisition & runtime", 2, 1, 2, 1, "data"),
             ("Intelligence", 0, 2, 4, 1, "decision"), ("Operations", 0, 3, 2, 1, "domain"), ("Compliance", 2, 3, 2, 1, "decision")]
    for lab, c, r, w, h, k in zones:
        x, y = xy(c, r)
        d.zone(x - 8, y - 12, w * cw + (w - 1) * gx + 16, h * ch + (h - 1) * gy + 20, lab, k, dash=None, sw=0.8, rx=12)
    for mid, (c, r) in pos.items():
        x, y = xy(c, r)
        mod = m[mid]
        k = kinds.get(mod["area"], "domain")
        if mid == "M14":
            k = "ai"
        d.box(x, y, cw, ch, f'{mod["name"]}', mod["code"].split(",")[0].replace("services/intelligence/", "intelligence/"), k, mod["status"], note=mod["entities"], tsize=11.5, ssize=7.6, nsize=8.6)
        d.text(x + cw - 8, y + ch - 7, mid, 8, 500, C["slate2"], "end", "mono")
    # key flows
    def right(c, r): x, y = xy(c, r); return (x + cw, y + ch / 2)
    def left(c, r): x, y = xy(c, r); return (x, y + ch / 2)
    def bottom(c, r, f=0.5): x, y = xy(c, r); return (x + cw * f, y + ch)
    def topp(c, r, f=0.5): x, y = xy(c, r); return (x + cw * f, y)
    a = bottom(2, 1, 0.3); b = topp(0, 2, 0.7)
    d.arrow([a, (a[0], a[1] + 14), (b[0], a[1] + 14), b], "async", "readings → HUMS", lpos=((a[0] + b[0]) / 2, a[1] + 14))
    d.arrow([right(0, 2), left(1, 2)], "sync", "")
    d.arrow([right(1, 2), left(2, 2)], "sync", "")
    d.arrow([right(2, 2), left(3, 2)], "sync", "")
    a = bottom(0, 2, 0.35); b = topp(1, 3, 0.35)
    d.arrow([a, (a[0], a[1] + 16), (b[0], a[1] + 16), b], "sync", "findings", lpos=(a[0] + 60, a[1] + 16))
    d.arrow([left(1, 3), right(0, 3)], "sync")
    d.arrow([right(1, 3), left(2, 3)], "sync", "")
    d.arrow([right(2, 3), left(3, 3)], "sync", "", both=True)
    # side panel
    px, py = xy(4, 2)
    d.rect(px - 8, py - 12, cw + 16, 2 * ch + gy + 20, fill=C["white"], stroke=C["line"], rx=12)
    d.text(px + 4, py + 6, "DATA OWNERSHIP RULE", 8, 500, C["slate"], face="mono", ls=1.2)
    d.mtext(px + 4, py + 24, "A module writes only its own tables. Others read through its service functions or derived views. "
            "Intelligence modules own signals, not the facts they read.", cw - 6, 10, 400, C["ink"], lh=1.3)
    d.status_legend(px + 4, py + 128, ["VERIFIED", "PARTIAL", "DESIGNED", "PROPOSED"], cols=2, colw=94, size=7.6)
    d.arrow_legend(px + 4, py + 186, ["sync", "async"], 1, lab={"sync": "In-process call", "async": "Job / in-transaction hand-off"})
    d.text(20, 18, "D03 · BACKEND MODULAR MONOLITH — ONE DEPLOYABLE, 18 MODULES", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1020, 18, "CURRENT VERIFIED ARCHITECTURE", 9, 500, C["teal"], "end", "mono", ls=1.2)
    return d


# ================================================================== D4 infrastructure topology
def d04_infra():
    d = Diagram(1040, 650, dark=True, title="D04 Infrastructure topology")
    # zones / trust boundaries
    d.zone(16, 60, 158, 462, "Public · untrusted", "risk", fill="#0B1F33")
    d.zone(190, 60, 150, 462, "Edge · TLS", "infra", fill="#0B2238")
    d.zone(356, 60, 300, 462, "Kota runtime · trusted", "domain", fill="#0B2540")
    d.zone(672, 60, 186, 462, "Data tier · restricted", "data", fill="#0B2540")
    d.zone(874, 60, 150, 462, "External providers", "ext", fill="#0B1F33")
    # public
    d.box(28, 74, 134, 70, "Browser users", "JWT bearer, no cookies", "user", tsize=11.5)
    d.box(28, 164, 134, 84, "Drones · gateways", "MAVLink UDP/TCP, HTTP push", "ext", "EXTERNAL", tsize=11.5)
    d.box(28, 268, 134, 70, "MQTT brokers", "TLS subscriber", "ext", "EXTERNAL", tsize=11.5)
    d.box(28, 358, 134, 84, "OEM · DJI clouds", "signed webhooks · REST pull", "ext", "EXTERNAL", tsize=11.5)
    # edge
    d.box(202, 74, 126, 84, "Frontend CDN", "Next.js on Vercel (reported)", "infra", "VERIFY", tsize=11.5)
    d.box(202, 178, 126, 84, "API ingress", "managed TLS · Render (reported)", "infra", "VERIFY", tsize=11.5)
    d.box(202, 282, 126, 96, "Device ingress", "UDP/TCP ports · CIDR allow-list · MAVLink-2 signing", "infra", "VERIFIED", tsize=11.5)
    # runtime
    d.box(370, 74, 272, 104, "API service", "uvicorn · FastAPI · app.main:asgi_app", "infra", "VERIFIED",
          note="AuthN → RBAC → tenant scope → entitlement; rate-limit policies; LISA model gateway in-process", tsize=12.5)
    d.box(370, 196, 132, 116, "Listeners", "python -m app.listeners", "data", "VERIFIED",
          note="UDP/TCP MAVLink, MQTT → bounded JobSink", tsize=11.5)
    d.box(510, 196, 132, 116, "Worker + scheduler", "python -m app.worker --schedule", "domain", "VERIFIED",
          note="claims jobs; retention, dunning, OEM polls", tsize=11.5)
    d.box(370, 344, 272, 56, "Rate limiter backend", "memory (default) · Redis (shared)", "risk", "PARTIAL", tsize=11.5)
    d.pill(436, 418, "retry · backoff · dead-letter · stale reclaim", 8.2, "#3A2328", C["coral"], C["coral"])
    d.pill(576, 440, "back-pressure: 5 000 queued / org", 8.2, "#3A2328", C["coral"], C["coral"])
    d.pill(506, 462, "fail-closed: ingest · webhook · LISA · admin", 8.2, "#3A2328", C["coral"], C["coral"])
    # data tier
    d.box(684, 74, 162, 168, "PostgreSQL 16", "managed (Neon, reported)", "data", "VERIFIED", tsize=13,
          note="OLTP + telemetry tables · audit_events (append-only) · background_jobs (queue, outbox-equivalent) · derived graph views")
    d.box(684, 258, 162, 66, "Object storage", "S3 API · MinIO locally", "data", "VERIFIED", tsize=11.5)
    d.box(684, 338, 162, 56, "Redis", "optional · rate limits", "data", "PARTIAL", tsize=11.5)
    d.box(684, 408, 162, 50, "Neo4j", "ADR-003 · unused", "ext", "SUPERSEDED", tsize=11.5)
    d.box(684, 466, 162, 46, "Message broker", "none by design", "ext", "PROPOSED", tsize=11, ssize=7.4)
    # external
    d.box(886, 74, 126, 72, "LLM provider", "Anthropic / OpenAI-compat.", "ai", "EXTERNAL", tsize=11.5)
    d.box(886, 160, 126, 64, "Email (SMTP)", "verification codes", "ext", "EXTERNAL", tsize=11.5)
    d.box(886, 238, 126, 64, "Payment provider", "test provider only", "ext", "EXTERNAL", tsize=11.5)
    d.box(886, 316, 126, 78, "OEM REST APIs", "outbound, SSRF-guarded", "ext", "EXTERNAL", tsize=11.5)
    d.box(886, 406, 126, 96, "Backup · PITR", "provider snapshots; restore drill not evidenced", "risk", "VERIFY", tsize=11.5)
    # observability band
    d.zone(16, 544, 1008, 92, "Observability plane", "gov", fill="#0B2238")
    obs = [("Structured logs", "structlog JSON · request_id · tenant", "VERIFIED"), ("Metrics endpoints", "API /platform/metrics · worker :9101 · listeners :9102", "VERIFIED"),
           ("Health", "/health · /health/ready (schema head + jobs)", "VERIFIED"), ("Scrape · alerting · dashboards", "Prometheus / Grafana", "PROPOSED")]
    for i, (t, s, st) in enumerate(obs):
        d.box(30 + i * 248, 562, 236, 60, t, s, "gov", st, tsize=11.5)
    # connectors
    d.arrow([(162, 109), (202, 109)], "sync")
    d.arrow([(328, 109), (370, 109)], "sync", "HTTPS")
    d.arrow([(162, 206), (186, 206), (186, 330), (202, 330)], "async")
    d.arrow([(162, 303), (202, 303)], "async")
    d.arrow([(328, 326), (436, 326), (436, 312)], "async", "frames", lpos=(384, 326))
    d.arrow([(162, 400), (190, 400), (190, 220), (202, 220)], "sync")
    d.arrow([(328, 220), (350, 220), (350, 150), (370, 150)], "sync", "")
    d.arrow([(642, 110), (684, 110)], "data", "SQL")
    d.arrow([(436, 196), (436, 188), (664, 188), (664, 200), (684, 200)], "async", "enqueue", lpos=(470, 188))
    d.arrow([(642, 236), (684, 236)], "data", "claim")
    d.arrow([(642, 160), (672, 160), (672, 284), (684, 284)], "data")
    d.arrow([(642, 372), (684, 372)], "data")
    d.arrow([(846, 100), (886, 100)], "sync", "")
    d.arrow([(600, 74), (600, 42), (872, 42), (872, 96), (886, 96)], "sync", "LISA model calls", lpos=(736, 42))
    d.arrow([(620, 74), (620, 48), (866, 48), (866, 190), (886, 190)], "sync")
    d.arrow([(576, 312), (576, 333), (878, 333), (878, 352), (886, 352)], "sync", "OEM poll", lpos=(780, 333))
    d.arrow([(846, 170), (860, 170), (860, 440), (886, 440)], "data", "backup", lpos=(860, 300))
    for x in (130, 440, 600, 760):
        d.arrow([(x, 522), (x, 560)], "obs")
    # legends
    d.text(16, 24, "D04", 11, 600, C["amber"], face="mono", ls=1.5)
    d.text(48, 24, "INFRASTRUCTURE TOPOLOGY", 11, 600, C["white"], face="mono", ls=1.5)
    d.text(1024, 24, "HYBRID · RUNTIME VERIFIED IN CODE · HOSTING REPORTED", 9, 500, "#A9BDD3", "end", "mono", ls=1.2)
    return d


# ================================================================== D5 drone-to-cloud connectivity
def d05_connectivity():
    d = Diagram(1040, 676, title="D05 Drone-to-cloud connectivity")
    cols = [(14, 156, "On the aircraft", "user"), (184, 124, "Transport", "ext"), (322, 166, "Cloud ingress", "infra"),
            (502, 166, "Validate & map", "data"), (682, 160, "Persist & evaluate", "domain"), (856, 170, "Act", "decision")]
    for x, w, lab, k in cols:
        d.zone(x, 52, w, 300, lab, k, dash=None if k != "ext" else "5 4", sw=0.9)
    # aircraft
    d.box(24, 70, 136, 50, "Sensors · ESCs · battery", None, "user", tsize=11)
    d.box(24, 132, 136, 76, "Flight controller", "PX4 / ArduPilot · emits MAVLink", "user", "EXTERNAL", tsize=11.5)
    d.box(24, 222, 136, 118, "Companion computer", "Pi / Jetson · mavlink-router", "data", "PARTIAL", tsize=11.5,
          note="Kota gateway daemon: normalise, buffer, uplink, heartbeat")
    d.arrow([(92, 120), (92, 132)], "sync")
    d.arrow([(92, 208), (92, 222)], "sync", "serial / UART", lpos=(92, 214))
    # transport
    tr = [("Cellular LTE / 5G", "EXTERNAL"), ("Wi-Fi", "EXTERNAL"), ("Satellite", "EXTERNAL"), ("Radio → GCS relay", "EXTERNAL")]
    for i, (t, st) in enumerate(tr):
        d.chip(194, 72 + i * 66, 104, 54, t, "IP link" if i < 3 else "915 MHz / 2.4 GHz", "ext", st, 10.5, 7.2)
    # ingress
    ing = [("UDP / TCP listener", "allow-list · MAVLink-2 signing", "VERIFIED"), ("HTTP push", "/data-sources/{id}/ingest", "VERIFIED"),
           ("MQTT subscriber", "TLS · topic filter · backoff", "VERIFIED"), ("Signed webhooks", "DJI · generic HMAC ±5 min", "VERIFIED")]
    for i, (t, s, st) in enumerate(ing):
        d.chip(332, 72 + i * 66, 146, 54, t, s, "infra", st, 10.8, 7.2)
    # validate
    va = [("Connector decode", "CRC_EXTRA · seq · dup · loss", "VERIFIED"), ("Canonical event", "NormalizedTelemetryEvent", "VERIFIED"),
          ("Quality gate", "finite · time window · ≥2000", "VERIFIED"), ("Asset & tenant map", "unknown → QUARANTINED", "VERIFIED")]
    for i, (t, s, st) in enumerate(va):
        d.chip(512, 72 + i * 66, 146, 54, t, s, "data", st, 10.8, 7.2)
        if i:
            d.arrow([(585, 72 + i * 66 - 12), (585, 72 + i * 66)], "sync")
    # persist
    pe = [("Event log + readings", "telemetry_event_logs · hums_sensor_readings", "VERIFIED"), ("Flight session", "advisory lock per asset", "VERIFIED"),
          ("HUMS evaluation", "per-event SAVEPOINT", "VERIFIED"), ("Source health", "HEALTHY → FAILED evidence", "VERIFIED")]
    for i, (t, s, st) in enumerate(pe):
        d.chip(692, 72 + i * 66, 140, 54, t, s, "domain", st, 10.8, 7.2)
    # act
    ac = [("M7 signal", "one per exceedance", "VERIFIED"), ("LISA explanation", "grounded tools", "VERIFIED"),
          ("Finding → work order", "human-created", "VERIFIED"), ("Fleet freshness", "stale-source gauges", "VERIFIED")]
    for i, (t, s, st) in enumerate(ac):
        d.chip(866, 72 + i * 66, 150, 54, t, s, "decision", st, 10.8, 7.2)
    # main arrows — buses make the many-to-many explicit (any link can carry any ingress protocol)
    ys = [99 + i * 66 for i in range(4)]
    d.line(176, 99, 176, ys[-1], C["cyan"], 1.6)
    d.arrow([(160, 280), (176, 280)], "async")
    for y in ys:
        d.arrow([(176, y), (194, y)], "async")
    d.line(314, 99, 314, ys[-1], C["cyan"], 1.6)
    for y in ys:
        d.line(298, y, 314, y, C["cyan"], 1.6, "6 4")
        d.arrow([(314, y), (332, y)], "async")
    d.line(494, 99, 494, ys[-1], C["ink"], 1.4)
    for y in ys:
        d.line(478, y, 494, y, C["ink"], 1.4)
    d.arrow([(494, 99), (512, 99)], "sync")
    d.arrow([(658, ys[3]), (675, ys[3]), (675, ys[0]), (692, ys[0])], "data")
    for i in range(1, 4):
        d.arrow([(762, 72 + i * 66 - 12), (762, 72 + i * 66)], "sync")
    d.arrow([(832, ys[2]), (849, ys[2]), (849, ys[0]), (866, ys[0])], "sync")
    d.arrow([(832, ys[2]), (866, ys[2])], "sync")
    d.arrow([(832, ys[3]), (866, ys[3])], "sync")
    d.arrow([(941, 126), (941, 138)], "sync")
    d.text(405, 344, "sync, or async job", 8.2, 400, C["slate"], "middle", "mono")
    # alternative paths
    d.zone(14, 378, 1002, 186, "Alternative acquisition paths", "ext", dash="5 4", sw=0.9, fill="#F9FAFC")
    alts = [("A", "Connected-aircraft service", "DJI FlightHub 2 · OEM cloud → signed webhook or credentialed REST poll", "VERIFIED", "software verified; real FlightHub / OEM tenancy external"),
            ("B", "Ground station · edge relay", "GCS or mavlink-router forwards UDP/TCP to the listener; no laptop in the loop", "EXTERNAL", "needs a physical relay and network path"),
            ("C", "Store-and-forward", "gateway queue drains after reconnect; arrival-time stamping today", "PARTIAL", "in-memory deque — proposed: disk queue + measured time"),
            ("D", "Automatic post-flight sync", "flight log (ULog / DataFlash) → batch connector after landing", "PROPOSED", "CSV / JSON batch exists; native log parsers not built"),
            ("E", "Manual import — fallback only", "operator uploads CSV / JSON through data import", "VERIFIED", "validation · quarantine · dedup")]
    for i, (k, t, s, st, n) in enumerate(alts):
        y = 396 + i * 33
        d.circle(34, y + 13, 10, fill=C["white"], stroke=C["slate"], sw=1)
        d.text(34, y + 17, k, 10, 700, C["slate"], "middle", "sans")
        d.text(54, y + 11, t, 11, 600, C["ink"])
        d.text(54, y + 24, s, 8.6, 400, C["slate"])
        d.badge(560, y + 4, st, "start", 8)
        d.text(660, y + 17, n, 9, 400, "#3A4A5C")
    # notes
    notes = [("MAVLink is a protocol, not an endpoint",
              "MAVLink frames describe vehicle state. Something on the aircraft or ground must turn the serial stream into an authenticated network flow (companion computer, GCS relay or OEM cloud). Kota's listener accepts that flow; it cannot reach a drone by itself.", "risk"),
             ("Ordering, duplicates, time",
              "Per-(sysid, compid) sequence: duplicates and late frames dropped, gaps counted as loss. Idempotency: unique (org, source_system, source_event_id). Time: MAVLink events carry arrival time today — buffered data loses true measurement time (finding F4).", "data"),
             ("Security & recovery",
              "CIDR allow-list and/or MAVLink-2 signing (replay-protected); webhooks HMAC with ±5 min window; tenant comes from the DataSource row, never the wire; per-event SAVEPOINT; quarantined events replay after mapping is fixed.", "gov")]
    for i, (t, s, k) in enumerate(notes):
        x = 14 + i * 340
        d.box(x, 578, 328, 90, t, None, k, note=s, tsize=11.5, nsize=9.2, accent_side="top")
    d.text(14, 22, "D05 · FIELD-TO-CLOUD CONNECTIVITY", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1016, 22, "HYBRID — SOFTWARE VERIFIED · PHYSICAL LINKS EXTERNAL", 9, 500, C["slate"], "end", "mono", ls=1.2)
    return d


# ================================================================== D6 HUMS processing
def d06_hums():
    d = Diagram(1040, 580, title="D06 HUMS processing architecture")
    stages = [("Raw readings", "hums_sensor_readings", "data", "VERIFIED"), ("Data quality", "VALID … OUT_OF_RANGE", "data", "VERIFIED"),
              ("Time alignment", "window N=20 · arrival time", "data", "PARTIAL"), ("Feature extraction", "RMS · kurtosis · DFT · trend", "domain", "VERIFIED"),
              ("Baseline", "versioned · z-score bands", "domain", "VERIFIED"), ("Signature match", "VIB-BRG / IMB / SEN", "domain", "VERIFIED"),
              ("Exceedance", "per-sensor limits · advisory lock", "decision", "VERIFIED"), ("Finding + evidence", "provenance: reading ids", "decision", "VERIFIED")]
    w, g, y = 117, 12, 70
    for i, (t, s, k, st) in enumerate(stages):
        x = 14 + i * (w + g)
        d.box(x, y, w, 84, t, s, k, tsize=11.2, ssize=7.2, accent_side="top")
        d.sicon(x + w - 10, y + 72, st, 6)
        d.text(x + 10, y + 77, f"{i+1:02d}", 9, 600, C["slate2"], face="mono")
        if i < len(stages) - 1:
            d.arrow([(x + w, y + 42), (x + w + g, y + 42)], "sync")
    # second row: outputs
    outs = [("Proactive signal (M7)", "HUMS_VIBRATION_EXCEEDANCE · DIAGNOSTIC_CANDIDATE · HEALTH_DEGRADATION · RUL_WARNING", "decision", "VERIFIED", 640),
            ("Fleet analytics (M14-ext)", "distributions over persisted rows — no recomputation", "decision", "VERIFIED", 440),
            ("LISA explanation", "get_asset_hums_* tools · UNKNOWN when data absent", "ai", "VERIFIED", 240),
            ("Maintenance workflow", "finding → work order (human) → evidence → release", "domain", "VERIFIED", 40)]
    for t, s, k, st, x in outs:
        d.box(x, 200, 180, 78, t, s, k, st, tsize=11.5, ssize=7.4)
    d.arrow([(14 + 7 * (w + g) + w / 2, 154), (14 + 7 * (w + g) + w / 2, 239), (820, 239)], "sync")
    d.line(700, 186, 130, 186, C["ink"], 1.4)
    d.line(700, 200, 700, 186, C["ink"], 1.4)
    for xx in (530, 330, 130):
        d.arrow([(xx, 186), (xx, 200)], "sync")
    d.pill(610, 186, "signals read by", 8.2)
    # feedback
    d.arrow([(130, 278), (130, 300), (560, 300), (560, 300), (624, 300), (624, 154)], "proposed", "confirmed outcome → baseline / signature tuning (proposed)", lpos=(380, 300))
    # H U D P RUL band
    band = [("H", "Health", "Is the component within its normal envelope?", "health_engine · HEALTHY / WATCH / DEGRADED", "VERIFIED"),
            ("U", "Usage", "How hard and how long has it worked?", "flights · hours · cycles · battery cycles", "VERIFIED"),
            ("D", "Diagnostics", "Which failure mode best explains the deviation?", "fault signatures + supporting / contradicting evidence", "VERIFIED"),
            ("P", "Prognostics", "Where is the trend going?", "degradation_engine · linear fit · drift check", "PARTIAL"),
            ("RUL", "Remaining useful life", "How long until a limit — with uncertainty?", "95% interval · 'ESTIMATE — NOT A CERTIFIED LIFE LIMIT'", "PARTIAL")]
    for i, (k, t, q, s, st) in enumerate(band):
        x = 14 + i * 204
        d.rect(x, 330, 196, 150, fill=C["white"], stroke=C["line"], rx=8)
        d.text(x + 14, 366, k, 26, 700, C["teal"] if st == "VERIFIED" else C["amberd"], face="disp")
        d.badge(x + 186, 340, st, "end", 7.6)
        d.text(x + 14, 388, t, 12, 600, C["ink"])
        d.mtext(x + 14, 406, q, 172, 10, 400, "#3A4A5C", lh=1.3)
        d.mtext(x + 14, 446, s, 172, 7.8, 400, C["slate"], face="mono", lh=1.3)
    # implemented vs proposed predictive
    d.rect(14, 496, 1012, 74, fill="#EFEBFB", stroke=C["purple"], rx=8, dash="2 4")
    d.text(30, 518, "PROPOSED — PREDICTIVE MODELS (NOT BUILT)", 8.6, 600, C["purpled"], face="mono", ls=1.2)
    d.mtext(30, 538, "Learned prognostic models per component class, fleet-relative baselines and rotor / eVTOL condition indicators (track & balance, gearbox CI, "
            "propulsor efficiency). Prerequisites: outcome-labelled maintenance data (confirmed removals), OEM data and a validation protocol. Until then RUL stays a "
            "deterministic linear estimate tagged AVAILABLE / LIMITED / INSUFFICIENT_DATA / LOW_CONFIDENCE / STALE.", 990, 10, 400, C["ink"], lh=1.35)
    d.text(14, 22, "D06 · HUMS PROCESSING CHAIN", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1026, 22, "CURRENT VERIFIED (DETERMINISTIC) + PROPOSED PREDICTIVE", 9, 500, C["slate"], "end", "mono", ls=1.2)
    return d


# ================================================================== D7 intelligence ownership & signal lifecycle
def d07_ownership():
    d = Diagram(1040, 626, title="D07 Intelligence ownership and signal lifecycle")
    lanes = [("HUMS", "producer of evidence", "domain", "Owns features, baselines, exceedances, diagnostic candidates, RUL records.", "Must not decide fleet priority or notify users."),
             ("M7", "signal authority", "decision", "Owns every actionable signal, telemetry freshness and fleet-attention rollups; signal lifecycle.", "Must not recompute HUMS maths; reads HUMS rows."),
             ("M14-ext", "descriptive analytics", "data", "Owns nothing persistent: bulk distributions over M7 and HUMS rows.", "Must not score health or create signals."),
             ("M4.2", "presentation & decision summary", "infra", "Owns the fleet control-center view: per-asset decision summary.", "Must not become a second signal source or vocabulary."),
             ("LISA", "explains & coordinates", "ai", "Owns conversation context; reads through authorised tools.", "Must not create, close or reword signals as fact.")]
    top, lh = 44, 76
    for i, (n, sub, k, owns, mustnot) in enumerate(lanes):
        y = top + i * lh
        d.rect(14, y, 1012, lh - 6, fill=KIND[k][1], rx=8)
        d.rect(14, y, 118, lh - 6, fill=KIND[k][0], rx=8)
        d.text(26, y + 30, n, 17, 700, C["white"] if k not in ("decision", "data") else C["ink"], face="disp")
        d.mtext(26, y + 48, sub, 100, 9, 500, C["white"] if k not in ("decision", "data") else C["ink"])
        d.mtext(732, y + 22, owns, 286, 9.6, 500, C["ink"], lh=1.25, max_lines=2)
        d.mtext(732, y + 50, "✕ " + mustnot, 286, 9.2, 400, C["corald"], lh=1.2, max_lines=2)
    d.line(722, top, 722, top + 5 * lh - 6, C["line"], 1)
    d.text(732, top - 8, "OWNERSHIP RULE", 8, 500, C["slate"], face="mono", ls=1.2)
    d.text(146, top - 8, "SIGNAL FLOW (VERIFIED IN CODE)", 8, 500, C["slate"], face="mono", ls=1.2)
    # flow nodes
    d.chip(146, top + 10, 132, 50, "Exceedance · diagnostic · RUL", "hums_* rows", "domain", "VERIFIED", 10)
    d.chip(300, top + 10, 132, 50, "Finding + evidence", "finding_service", "domain", "VERIFIED", 10)
    d.chip(146, top + lh + 10, 132, 50, "Rule evaluators", "8 evaluators · sync", "decision", "VERIFIED", 10)
    d.chip(300, top + lh + 10, 132, 50, "signal_key dedupe", "SAVEPOINT insert", "decision", "VERIFIED", 10)
    d.chip(454, top + lh + 10, 124, 50, "ProactiveSignalRecord", "status · severity", "decision", "VERIFIED", 10)
    d.chip(596, top + lh + 10, 112, 50, "Lifecycle API", "ack · review · …", "decision", "VERIFIED", 10)
    d.chip(454, top + 2 * lh + 10, 124, 50, "Fleet distributions", "bulk queries", "data", "VERIFIED", 10)
    d.chip(300, top + 3 * lh + 10, 132, 50, "Readiness → risk → priority", "per-asset cascade", "infra", "PARTIAL", 10)
    d.chip(454, top + 3 * lh + 10, 124, 50, "/intelligence/fleet", "M4.2 summary", "infra", "VERIFIED", 10)
    d.chip(454, top + 4 * lh + 10, 124, 50, "Signal & HUMS tools", "get_asset_proactive_…", "ai", "VERIFIED", 10)
    d.chip(596, top + 4 * lh + 10, 112, 50, "Grounded answer", "cites tools run", "ai", "VERIFIED", 10)
    d.arrow([(212, top + 60), (212, top + lh + 10)], "sync", "read", lpos=(212, top + 66))
    d.arrow([(278, top + 35), (300, top + 35)], "sync")
    d.arrow([(278, top + lh + 35), (300, top + lh + 35)], "sync")
    d.arrow([(432, top + lh + 35), (454, top + lh + 35)], "data")
    d.arrow([(578, top + lh + 35), (596, top + lh + 35)], "sync")
    d.arrow([(516, top + lh + 60), (516, top + 2 * lh + 10)], "sync", "read")
    d.arrow([(560, top + lh + 60), (560, top + lh + 67), (588, top + lh + 67), (588, top + 4 * lh + 22), (578, top + 4 * lh + 22)], "sync")
    d.arrow([(432, top + 3 * lh + 35), (454, top + 3 * lh + 35)], "sync")
    d.arrow([(578, top + 4 * lh + 35), (596, top + 4 * lh + 35)], "sync")
    d.arrow([(366, top + 3 * lh + 10), (366, top + 2 * lh + 66), (240, top + 2 * lh + 66), (240, top + lh + 60)], "prohibited", "second vocabulary (F7)", lpos=(300, top + 2 * lh + 66))
    # lifecycle state machine
    sy = 446
    d.text(14, sy - 12, "SIGNAL LIFECYCLE — proactive_signal_records.status", 8.6, 500, C["slate"], face="mono", ls=1.2)
    states = [("OPEN", 14, C["coral"]), ("ACKNOWLEDGED", 148, C["amberd"]), ("IN_REVIEW", 300, C["amberd"]), ("RESOLVED", 440, C["teal"])]
    for t, x, col in states:
        d.rect(x, sy, 116, 40, fill=C["white"], stroke=col, sw=1.6, rx=20)
        d.text(x + 58, sy + 25, t, 10.5, 600, col, "middle", "mono")
    d.arrow([(130, sy + 20), (148, sy + 20)], "human")
    d.arrow([(264, sy + 20), (300, sy + 20)], "human")
    d.arrow([(416, sy + 20), (440, sy + 20)], "human")
    d.rect(300, sy + 74, 116, 40, fill=C["white"], stroke=C["slate"], sw=1.6, rx=20)
    d.text(358, sy + 99, "DISMISSED", 10.5, 600, C["slate"], "middle", "mono")
    d.arrow([(72, sy + 40), (72, sy + 94), (300, sy + 94)], "human", "dismiss + reason", lpos=(186, sy + 94))
    d.arrow([(206, sy + 40), (206, sy + 84), (300, sy + 84)], "human")
    d.arrow([(498, sy + 40), (498, sy + 60), (40, sy + 60), (40, sy + 40)], "feedback", "condition still true on next sync → stays / re-opens", lpos=(270, sy + 60))
    d.mtext(14, sy + 136, "Every transition is a human action through the lifecycle API and writes an audit event (_audit_transition). "
            "Signals are created only by M7 sync (today triggered by reads — F6), never by LISA.", 560, 9.6, 400, "#3A4A5C", lh=1.3)
    # duplicate prevention
    d.box(600, sy - 10, 426, 132, "How duplicates and conflicts are prevented", None, "decision", note=
          "1 · One owner per signal type (M7) — other modules read.\n"
          "2 · Deterministic signal_key per source fact; concurrent sync inserts under SAVEPOINT and adopts the winner.\n"
          "3 · HUMS evaluation serialised per sensor (advisory lock): one exceedance, one finding.\n"
          "4 · M14-ext reads persisted rows; never calls write-on-read HUMS functions.\n"
          "5 · Proposed: signal-type registry, status filters from model constants, sync moved to jobs (F6, F7).",
          tsize=12, nsize=9.6, accent_side="top")
    d.text(14, 22, "D07 · INTELLIGENCE OWNERSHIP — HUMS · M7 · M14-ext · M4.2 · LISA", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1026, 22, "CURRENT VERIFIED + RULES", 9, 500, C["slate"], "end", "mono", ls=1.2)
    return d


# ================================================================== D8 LISA & agentic AI
def d08_lisa():
    d = Diagram(1040, 578, dark=True, title="D08 LISA and agentic AI architecture")
    # pipeline top row
    steps = [("User intent", "question · /lisa", "user", "VERIFIED"), ("Identity & tenant", "JWT → DB user · org", "infra", "VERIFIED"),
             ("Safety guard (in)", "airworthiness patterns", "risk", "VERIFIED"), ("Intent · entities", "reference resolution", "ai", "VERIFIED"),
             ("Context assembly", "conversation context", "ai", "VERIFIED"), ("Model gateway", "provider abstraction", "ai", "EXTERNAL")]
    w, g = 156, 15
    for i, (t, s, k, st) in enumerate(steps):
        x = 18 + i * (w + g)
        d.box(x, 58, w, 62, t, s, k, st, tsize=11.5, ssize=7.4)
        if i < len(steps) - 1:
            d.arrow([(x + w, 89), (x + w + g, 89)], "sync")
    # planning / registry / authz
    d.box(18, 150, 300, 94, "Tool registry · 61 tools", "services/ai/tools.py · ToolSpec", "ai", "VERIFIED",
          note="Each tool declares required_permission and required_feature. No tool accepts an organisation argument — tenant comes from the caller.", tsize=12.5)
    d.box(340, 150, 330, 94, "Per-call authorisation chain", "_require_permission → _require_entitlement", "gov", "VERIFIED",
          note="1 RBAC permission  2 subscription state  3 suite (multi-suite aware)  4 feature (any-of). Same resolver as REST. 257-case matrix test.", tsize=12.5)
    d.box(692, 150, 330, 94, "Planning & orchestration", "services/lisa/orchestration_service.py", "ai", "VERIFIED",
          note="Model selects tools; deterministic investigation graph for fleet / asset questions; tools_invoked returned with the answer.", tsize=12.5)
    d.arrow([(939, 120), (939, 150)], "sync")
    d.arrow([(692, 197), (670, 197)], "sync", "")
    d.arrow([(340, 197), (318, 197)], "sync")
    # tool classes
    d.zone(18, 272, 1004, 122, "Domain tools by effect", "ai", fill="#0B2238")
    cls = [("Read-only tools", "60 of 61 · fleet, HUMS, M7, MRO, parts, compliance, digital twin", "VERIFIED", "domain",
            "Return tenant-scoped facts or UNKNOWN / INSUFFICIENT_DATA."),
           ("Draft-producing tools", "work-order proposal · evidence checklist · obligation plan", "PROPOSED", "decision",
            "Produce a draft record in DRAFT state for a human to submit; never final."),
           ("State-changing tools", "run_assessment (ASSESSMENT_WRITE) today", "PARTIAL", "risk",
            "Deterministic engine writes; LISA only triggers. Proposed: explicit user confirmation + audit row for every call.")]
    for i, (t, s, st, k, n) in enumerate(cls):
        x = 32 + i * 330
        d.box(x, 290, 316, 88, t, s, k, st, note=n, tsize=12.5, ssize=7.6, nsize=9.6)
    d.arrow([(230, 244), (230, 290)], "sync", "authorised call", lpos=(310, 258))
    # output validation & approval & audit & feedback
    tail = [("Safety guard (out)", "tool results + final text", "risk", "VERIFIED"), ("Output validation", "grounding: cite tools run", "gov", "VERIFIED"),
            ("Human approval", "required for writes", "decision", "PROPOSED"), ("Execution", "domain service, same rules", "domain", "PARTIAL"),
            ("Audit", "AuditEvent per tool call", "gov", "PARTIAL"), ("Feedback", "answer rating · eval set", "ai", "PROPOSED")]
    for i, (t, s, k, st) in enumerate(tail):
        x = 18 + i * (w + g)
        d.box(x, 426, w, 62, t, s, k, st, tsize=11.5, ssize=7.4)
        if i < len(tail) - 1:
            d.arrow([(x + w, 457), (x + w + g, 457)], "sync" if i < 1 else ("human" if i in (1, 2) else "sync"))
    d.arrow([(520, 378), (520, 410), (96, 410), (96, 426)], "sync")
    # boundaries
    d.rect(18, 504, 1004, 60, fill="#3A2328", stroke=C["coral"], rx=8, dash="4 3")
    d.text(32, 524, "HARD BOUNDARIES", 8.6, 600, C["coral"], face="mono", ls=1.4)
    d.mtext(32, 542, "LISA never bypasses backend authorisation · never invents evidence (UNKNOWN when absent) · never certifies compliance, airworthiness or release to service "
            "(refused by the deterministic guard) · never executes a high-impact action without an approved human step · never writes system_result or final status.",
            976, 9.6, 400, "#F6D5CE", lh=1.3)
    d.text(18, 30, "D08", 11, 600, C["amber"], face="mono", ls=1.5)
    d.text(50, 30, "LISA & AGENTIC AI ARCHITECTURE", 11, 600, C["white"], face="mono", ls=1.5)
    d.text(1022, 30, "HYBRID · TOOLS VERIFIED · GOVERNED WRITES PROPOSED", 9, 500, "#A9BDD3", "end", "mono", ls=1.2)
    return d


# ================================================================== D9 compliance & evidence
def d09_compliance():
    d = Diagram(1040, 600, title="D09 Compliance and evidence architecture")
    cols = [("Source material", "ext", 14), ("Internal interpretation", "decision", 272), ("Executable rule logic", "domain", 530), ("Evaluation output", "data", 788)]
    for lab, k, x in cols:
        d.zone(x, 46, 238, 300, lab, k, dash=None, sw=0.9)
    d.box(28, 66, 210, 64, "Regulatory authority", "reference entity · not a tenant", "ext", "VERIFIED", tsize=11.5)
    d.box(28, 146, 210, 80, "Regulatory document", "regulatory_documents · revision · source_url", "ext", "VERIFIED", tsize=11.5)
    d.box(28, 242, 210, 90, "Customer requirement", "requirement_type = OTHER · NOTICE", "ext", "VERIFIED", tsize=11.5,
          note="Customer or contract obligations use the same chain.")
    d.box(286, 66, 210, 112, "Versioned requirement", "regulatory_requirements · AD | SB | AMC | GM | SIB…", "decision", "VERIFIED", tsize=11.5,
          note="type_metadata jsonb; references_requirement_id links AD → SB.")
    d.box(286, 194, 210, 138, "Rule versioning & effective dates", "applicability_rules.is_active only", "risk", "PROPOSED", tsize=11.5,
          note="Today a rule is edited in place. Proposed: rule_version, effective_from/to, supersedes_id — old evaluations keep their rule version.")
    d.box(544, 66, 210, 96, "Applicability rule", "applicability_rules → condition tree", "domain", "VERIFIED", tsize=11.5,
          note="AND / OR / NOT nodes with typed parameters.")
    d.box(544, 176, 210, 70, "Kleene evaluator", "TRUE · FALSE · UNKNOWN", "domain", "VERIFIED", tsize=11.5, note="UNKNOWN never collapses to FALSE.")
    d.box(544, 260, 210, 72, "Evaluation inputs", "as-of configuration · asset family", "domain", "VERIFIED", tsize=11.5)
    d.box(802, 66, 210, 96, "Applicability evaluation", "system_result · configuration_snapshot · reasoning_trace", "data", "VERIFIED", tsize=11.5)
    d.box(802, 176, 210, 76, "Compliance obligation", "due_date · recurrence · required_action", "data", "VERIFIED", tsize=11.5)
    d.box(802, 266, 210, 66, "Compliance finding / state", "DUE · OVERDUE · COMPLIANT · BLOCKED…", "data", "VERIFIED", tsize=11.5)
    for y in (98, 186, 287):
        pass
    d.arrow([(133, 130), (133, 146)], "sync")
    d.arrow([(238, 186), (262, 186), (262, 122), (286, 122)], "sync")
    d.arrow([(238, 287), (270, 287), (270, 150), (286, 150)], "sync")
    d.arrow([(496, 114), (544, 114)], "sync", "authored")
    d.arrow([(649, 162), (649, 176)], "sync")
    d.arrow([(649, 260), (649, 246)], "sync")
    d.arrow([(754, 211), (778, 211), (778, 114), (802, 114)], "data", "")
    d.arrow([(907, 162), (907, 176)], "data")
    d.arrow([(907, 252), (907, 266)], "data")
    # bottom: evidence, review, approval, audit, lifecycle
    d.zone(14, 372, 1012, 130, "History", "gov", dash=None, sw=0.9)
    row = [("Evidence association", "evidence → obligation · requirement · task", "gov", "VERIFIED"),
           ("Human review", "ACCEPTED / REJECTED · reviewer_user_id", "decision", "VERIFIED"),
           ("Decision lineage (ADR-005)", "human_decision · final_status · previous id", "decision", "DESIGNED"),
           ("Audit trail", "audit_events · DB trigger blocks UPDATE/DELETE", "gov", "VERIFIED"),
           ("Lifecycle update", "next due from recurrence · re-evaluate", "data", "VERIFIED")]
    for i, (t, s, k, st) in enumerate(row):
        x = 28 + i * 200
        d.box(x, 392, 186, 96, t, s, k, st, tsize=11.5, ssize=7.4)
        if i < 4:
            d.arrow([(x + 186, 440), (x + 200, 440)], "human" if i in (0, 1) else "sync")
    d.arrow([(907, 332), (907, 358), (180, 358), (180, 392)], "sync", "evidence required", lpos=(500, 358))
    d.arrow([(921, 488), (921, 512), (1020, 512), (1020, 220), (1012, 220)], "feedback")
    # rules strip
    d.rect(14, 524, 1012, 64, fill=C["white"], stroke=C["line"], rx=8)
    d.text(28, 546, "PRESERVING HISTORY", 8.6, 600, C["teal"], face="mono", ls=1.2)
    d.mtext(28, 564, "Document revisions are rows, not overwrites. Each evaluation stores the configuration it saw and its reasoning trace, so a past decision can be re-derived "
            "and compared. Gaps: rule edits are not versioned and the system / human / final decision chain of ADR-005 is not in the schema (finding F8).",
            950, 9.8, 400, C["ink"], lh=1.3)
    d.text(14, 22, "D09 · COMPLIANCE & EVIDENCE — SOURCE → INTERPRETATION → LOGIC → OUTPUT", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1026, 22, "HYBRID", 9, 500, C["slate"], "end", "mono", ls=1.2)
    return d


# ================================================================== D10 MRO & asset lifecycle
def d10_mro():
    d = Diagram(1040, 560, title="D10 MRO and asset lifecycle")
    nodes = [("Asset onboarding", "registry · suite family", "infra"), ("Configuration", "serials · installations", "infra"), ("Utilisation", "flights · hours · cycles", "data"),
             ("Inspection", "requirements · RII", "domain"), ("Defect / finding", "severity · disposition", "decision"), ("Work order", "DRAFT → OPEN → …", "domain"),
             ("Tasks", "execution · evidence_required", "domain"), ("Parts & resources", "requirements · inventory · PO", "domain"), ("Evidence capture", "files · checksum", "gov"),
             ("Authorised review", "inspection sign-off", "decision"), ("Release readiness", "READY / BLOCKED gate", "decision"), ("Next due state", "programme · recurrence", "data"),
             ("Lifecycle record", "audit · installation history", "gov")]
    # racetrack positions: top row 0-4 L→R, right 5, bottom 6-10 R→L, left 11-12
    W, H = 158, 62
    pos = [(40, 70), (232, 70), (424, 70), (616, 70), (808, 70),
           (842, 196),
           (808, 322), (616, 322), (424, 322), (232, 322), (40, 322),
           (6, 196), (6, 196)]
    order = list(range(11))
    for i in range(11):
        x, y = pos[i]
        t, s, k = nodes[i]
        d.box(x, y, W, H, t, s, k, "VERIFIED", tsize=11.5, ssize=7.4)
        d.text(x + W - 8, y + H - 7, f"{i+1:02d}", 8, 600, C["slate2"], "end", "mono")
    # left column: next due + lifecycle record stacked
    d.box(6, 172, 150, 52, nodes[11][0], nodes[11][1], "data", "VERIFIED", tsize=11, ssize=7.2)
    d.box(6, 236, 150, 52, nodes[12][0], nodes[12][1], "gov", "VERIFIED", tsize=11, ssize=7.2)
    d.text(148, 220, "12", 8, 600, C["slate2"], "end", "mono")
    d.text(148, 284, "13", 8, 600, C["slate2"], "end", "mono")
    for i in range(4):
        x, y = pos[i]
        d.arrow([(x + W, y + H / 2), (pos[i + 1][0], y + H / 2)], "sync")
    d.arrow([(966, 101), (1020, 101), (1020, 227), (1000, 227)], "sync")
    d.box(842, 196, 158, 62, nodes[5][0], nodes[5][1], "domain", "VERIFIED", tsize=11.5, ssize=7.4)
    d.arrow([(921, 258), (921, 290), (887, 290), (887, 322)], "sync")
    for i in range(6, 10):
        x, y = pos[i]
        d.arrow([(x, y + H / 2), (pos[i + 1][0] + W, y + H / 2)], "sync")
    d.arrow([(119, 322), (119, 300), (81, 300), (81, 288)], "sync")
    d.arrow([(81, 236), (81, 224)], "sync")
    d.arrow([(81, 172), (81, 132)], "feedback", "next cycle", lpos=(81, 152))
    # centre: inputs and gates
    d.rect(200, 158, 620, 132, fill=C["white"], stroke=C["line"], rx=12)
    d.text(216, 178, "INPUTS THAT OPEN OR INFORM WORK — NEVER BYPASS AUTHORISATION", 8.4, 600, C["slate"], face="mono", ls=1.1)
    ins = [("HUMS finding", "exceedance → finding + evidence (automatic)", "decision", "VERIFIED"),
           ("M7 signal", "user creates work order from signal", "decision", "VERIFIED"),
           ("Compliance obligation", "due / overdue → planned work", "decision", "VERIFIED")]
    for i, (t, s, k, st) in enumerate(ins):
        d.box(216 + i * 200, 190, 188, 60, t, s, k, st, tsize=11, ssize=7.2)
    d.text(216, 270, "Gates: tasks complete → INSPECTION · RII by a second person · evidence ACCEPTED · READY = zero blockers", 9.2, 500, C["ink"])
    d.arrow([(820, 227), (842, 227)], "human")
    d.pill(760, 274, "→ authorised user creates / plans", 8.4, C["white"], C["amberd"], C["amberd"])
    # legend
    d.rect(14, 410, 1012, 136, fill="#FFFFFF", stroke=C["line"], rx=10)
    d.text(30, 432, "WORK ORDER STATE MACHINE (models/work_order.py)", 8.6, 600, C["slate"], face="mono", ls=1.2)
    states = ["DRAFT", "OPEN", "PLANNED", "ASSIGNED", "IN_PROGRESS", "INSPECTION", "COMPLETED", "CLOSED"]
    for i, st in enumerate(states):
        x = 30 + i * 122
        d.rect(x, 446, 108, 30, fill=KIND["domain"][1], stroke=C["teal"], rx=15)
        d.text(x + 54, 465, st, 9.4, 600, C["teal"], "middle", "mono")
        if i < 7:
            d.arrow([(x + 108, 461), (x + 122, 461)], "sync")
    d.rect(518, 494, 108, 30, fill="#F1F3F6", stroke=C["slate"], rx=15)
    d.text(572, 513, "ON_HOLD", 9.4, 600, C["slate"], "middle", "mono")
    d.rect(640, 494, 108, 30, fill="#FDECE8", stroke=C["coral"], rx=15)
    d.text(694, 513, "CANCELLED", 9.4, 600, C["corald"], "middle", "mono")
    d.mtext(30, 500, "Every transition writes work_order.transitioned (audit). "
            "IN_PROGRESS → INSPECTION needs all tasks complete; INSPECTION → COMPLETED needs inspections passed.", 470, 9.4, 400, "#3A4A5C", lh=1.3)
    d.mtext(770, 500, "Return to service is a human determination outside LISA.", 240, 9.4, 600, C["corald"], lh=1.3)
    d.text(14, 22, "D10 · MRO & ASSET LIFECYCLE", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1026, 22, "CURRENT VERIFIED", 9, 500, C["teal"], "end", "mono", ls=1.2)
    return d


# ================================================================== D11 suite, plan & entitlement
def d11_entitlements():
    d = Diagram(1040, 560, title="D11 Suite, plan and entitlement architecture")
    d.zone(14, 46, 700, 170, "Commercial entitlement — what the organisation bought", "gov", dash=None, sw=0.9)
    d.zone(14, 250, 700, 150, "User authorisation — what this person may do", "infra", dash=None, sw=0.9)
    com = [("Organization", "status ACTIVE (not suspended)", "VERIFIED"), ("Suite selection", "AIRCRAFT · DRONE_UAV · HELICOPTER · EVTOL_AAM", "VERIFIED"),
           ("Suite-specific plan", "UNIQUE(suite, code)", "VERIFIED"), ("Subscription", "TRIALING · ACTIVE · PAST_DUE grant", "VERIFIED"),
           ("Effective features & limits", "plan features + tenant overrides + limits", "VERIFIED")]
    w, g = 124, 14
    for i, (t, s, st) in enumerate(com):
        x = 28 + i * (w + g)
        d.box(x, 70, w, 92, t, s, "gov", st, tsize=11, ssize=7.2)
        if i < 4:
            d.arrow([(x + w, 116), (x + w + g, 116)], "sync")
    d.mtext(28, 182, "One subscription per org per suite; two current subscriptions in the same suite = AMBIGUOUS → deny. Resolved on every request, no cache, no JWT claims.",
            670, 9.4, 400, "#3A4A5C", lh=1.3)
    usr = [("User", "DB-authoritative per request", "VERIFIED"), ("Roles", "user_roles (not token claims)", "VERIFIED"),
           ("Permissions", "Permission catalogue", "VERIFIED"), ("Resource ownership", "tenant · facility · asset · component", "VERIFIED")]
    w2 = 158
    for i, (t, s, st) in enumerate(usr):
        x = 28 + i * (w2 + 14)
        d.box(x, 274, w2, 80, t, s, "infra", st, tsize=11.5, ssize=7.2)
        if i < 3:
            d.arrow([(x + w2, 314), (x + w2 + 14, 314)], "sync")
    d.mtext(28, 376, "Foreign ids return 404 (no existence oracle). Deactivation or role removal takes effect on the next request.", 670, 9.4, 400, "#3A4A5C")
    # decision
    cx, cy = 790, 226
    d.raw(f'<path d="M{cx},{cy-60} L{cx+60},{cy} L{cx},{cy+60} L{cx-60},{cy} Z" fill="#FDF4E1" stroke="{C["amberd"]}" stroke-width="1.6"/>')
    d.text(cx, cy - 6, "Final access", 11.5, 600, C["ink"], "middle")
    d.text(cx, cy + 10, "decision", 11.5, 600, C["ink"], "middle")
    d.arrow([(714, 116), (790, 116), (790, 166)], "sync", "feature?", lpos=(752, 116))
    d.arrow([(714, 314), (790, 314), (790, 286)], "sync", "permission?", lpos=(752, 314))
    d.box(870, 120, 150, 50, "Allow", "both true", "domain", tsize=12)
    d.box(870, 186, 150, 62, "SUITE_ENTITLEMENT_ REQUIRED", "feature outside suite", "risk", tsize=10.5, ssize=7.2)
    d.box(870, 262, 150, 50, "forbidden (403)", "in-suite, not purchased · no permission", "risk", tsize=11, ssize=7.0)
    d.box(870, 326, 150, 50, "usage_limit_exceeded", "max assets · users · WOs · storage", "risk", tsize=10.5, ssize=7.0)
    d.arrow([(850, 226), (860, 226), (860, 145), (870, 145)], "sync")
    d.arrow([(850, 226), (870, 217)], "sync")
    d.arrow([(850, 226), (860, 226), (860, 287), (870, 287)], "sync")
    d.arrow([(850, 226), (860, 226), (860, 351), (870, 351)], "sync")
    # enforcement points
    d.zone(14, 432, 1012, 116, "Enforcement points — same resolver everywhere", "decision", dash=None, sw=0.9)
    ep = [("Frontend", "sidebar = route guard · display only", "VERIFIED"), ("REST API", "require_feature at router level", "VERIFIED"),
          ("LISA tools", "_require_entitlement per call", "VERIFIED"), ("Usage limits", "limit_enforcement_service", "VERIFIED"),
          ("Workers · listeners · pollers", "no entitlement re-check (F3)", "PARTIAL"), ("Platform admin", "catalogue · plans · overrides", "VERIFIED")]
    for i, (t, s, st) in enumerate(ep):
        x = 28 + i * 166
        d.box(x, 452, 156, 82, t, s, "decision" if st == "VERIFIED" else "risk", st, tsize=11.5, ssize=7.2)
    d.text(14, 22, "D11 · SUITE → PLAN → SUBSCRIPTION → ENTITLEMENT, AND USER AUTHORISATION", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1026, 22, "CURRENT VERIFIED (+ GAP F3)", 9, 500, C["slate"], "end", "mono", ls=1.2)
    return d


# ================================================================== D12 security & trust boundaries
def d12_security():
    d = Diagram(1040, 600, dark=True, title="D12 Security and trust boundaries")
    d.zone(14, 50, 760, 536, "Public internet", "risk", fill="#0A1D30")
    d.zone(36, 92, 716, 478, "Authenticated callers · JWT / HMAC / signed MAVLink", "infra", fill="#0B2238")
    d.zone(58, 134, 672, 420, "Tenant boundary · organization_id on every row", "gov", fill="#0C2A40", dash="6 3")
    d.zone(80, 176, 628, 362, "Internal services · single trusted runtime", "domain", fill="#0D3048", dash=None)
    d.zone(102, 382, 584, 140, "Data stores · restricted network", "data", fill="#0E2F4A")
    d.text(360, 80, "edge protection (WAF / DDoS): provider-side, not in repo — proposed", 8.8, 400, "#F6B3A6")
    d.text(60, 124, "TLS · JWT exp + sub required · alg=none rejected · Argon2 · DB re-check every request · HMAC ±5 min · MAVLink-2 signing", 8.8, 400, "#A9C8EE")
    d.text(82, 166, "foreign ids → 404 · tenant never taken from the wire · cross-tenant probe over the route table", 8.8, 400, C["mint"])
    # internal
    d.box(102, 200, 180, 84, "API + domain services", "RBAC · tenant scope · entitlement", "infra", "VERIFIED", tsize=11.5)
    d.box(296, 200, 180, 84, "AI gateway (LISA)", "same authz chain · safety guard", "ai", "PARTIAL", tsize=11.5,
          note="no separate DB role (F5)")
    d.box(490, 200, 196, 84, "Workers · listeners", "job context binds tenant", "domain", "PARTIAL", tsize=11.5, note="entitlement re-check missing (F3)")
    d.box(102, 298, 584, 66, "Cross-cutting controls", "rate-limit policies (fail-closed for ingest, webhook, LISA, admin) · security headers · CORS allow-list · 25 MB body cap · JSON-only errors", "gov", "VERIFIED", tsize=11.5, ssize=7.6)
    d.box(116, 404, 180, 104, "PostgreSQL", "parameterised SQL only", "data", "VERIFIED", tsize=11.5, note="audit_events immutable by trigger; tenant FK on every row")
    d.box(310, 404, 180, 104, "Object storage", "sanitised keys · SHA-256", "data", "VERIFIED", tsize=11.5, note="presigned URLs 300 s; WORM / object-lock not configured")
    d.box(504, 404, 168, 104, "Encryption at rest", "provider-managed (reported)", "data", "VERIFY", tsize=11.5, note="TLS in transit at the edge; KMS / CMK not in repo")
    # outside right
    d.box(792, 60, 232, 92, "Device identities", "edge_devices · token hash · revoke", "ext", "PARTIAL", tsize=11.5,
          note="HTTP push uses a tenant JWT; per-device machine credentials proposed")
    d.box(792, 166, 232, 82, "External providers", "LLM · SMTP · billing · OEM", "ext", "EXTERNAL", tsize=11.5,
          note="OEM pull: HTTPS only, public IPs, no redirects (SSRF guard)")
    d.box(792, 262, 232, 92, "Administrative control plane", "PLATFORM_ADMIN · platform:manage", "gov", "VERIFIED", tsize=11.5,
          note="four-eyes approval for expansive tenant changes; audited")
    d.box(792, 368, 232, 80, "Secrets", "env KOTA_SECRET_<ref> · secret_reference", "risk", "PARTIAL", tsize=11.5,
          note="no vault / rotation tooling in repo")
    d.box(792, 462, 232, 92, "Backup & recovery systems", "provider snapshots · retention archive", "risk", "VERIFY", tsize=11.5,
          note="separate credentials and restore drill required")
    d.arrow([(774, 106), (792, 106)], "async")
    d.arrow([(752, 207), (792, 207)], "sync")
    d.arrow([(730, 308), (792, 308)], "sync")
    d.arrow([(686, 456), (792, 508)], "data")
    d.text(14, 30, "D12", 11, 600, C["amber"], face="mono", ls=1.5)
    d.text(46, 30, "SECURITY & TRUST BOUNDARIES", 11, 600, C["white"], face="mono", ls=1.5)
    d.text(1024, 30, "HYBRID · NO CERTIFICATION CLAIMED", 9, 500, "#A9BDD3", "end", "mono", ls=1.2)
    return d


# ================================================================== D13 deployment & operations
def d13_deploy():
    d = Diagram(1040, 440, title="D13 Deployment and operations")
    envs = [("Local development", "ext", 14), ("Continuous integration", "infra", 272), ("Staging", "data", 530), ("Production", "decision", 788)]
    for lab, k, x in envs:
        d.zone(x, 46, 238, 220, lab, k, dash=None, sw=0.9)
    d.box(28, 66, 210, 90, "docker-compose", "infra/docker-compose.yml", "ext", "VERIFIED", tsize=11.5,
          note="PostgreSQL 16 · Redis 7 · MinIO · Neo4j 5 (started but unused — F1)")
    d.box(28, 168, 210, 88, "uvicorn · next dev", "README · .env.example", "ext", "VERIFIED", tsize=11.5,
          note="seed scripts for QA, HUMS, browser harness; platform admin bootstrap script")
    d.box(286, 66, 210, 108, "GitHub Actions · backend", ".github/workflows/ci.yml", "infra", "PARTIAL", tsize=11.5,
          note="ruff · mypy · alembic upgrade · pytest on Python 3.11 + PostgreSQL 16 · pip-audit (non-blocking). One test needs 3.12 (F9).")
    d.box(286, 184, 210, 74, "GitHub Actions · frontend", "npm lint · typecheck · build", "infra", "PARTIAL", tsize=11.5,
          note="vitest (383 tests) not run in CI · npm audit non-blocking")
    d.box(544, 66, 210, 56, "Frontend", "Vercel project 'aerocomply' (reported)", "data", "VERIFY", tsize=11.5)
    d.box(544, 132, 210, 56, "Backend container", "Dockerfile → Render (reported)", "data", "VERIFY", tsize=11.5)
    d.box(544, 198, 210, 58, "Database", "managed PostgreSQL · Neon (reported)", "data", "VERIFY", tsize=11.5)
    d.box(802, 66, 210, 88, "Production topology", "API ×N · worker · listeners", "decision", "PROPOSED", tsize=11.5,
          note="Shared Redis for rate limits; separate worker and listener processes; private DB network.")
    d.box(802, 164, 210, 94, "Preflight & go-live", "production_preflight.sql · checklist", "decision", "DESIGNED", tsize=11.5,
          note="Never touched by this audit. Pen test, capacity test, payment provider and UAT outstanding.")
    d.arrow([(238, 110), (286, 110)], "sync", "push / PR")
    d.arrow([(496, 120), (520, 120), (520, 94), (544, 94)], "sync", "")
    d.arrow([(496, 120), (520, 120), (520, 160), (544, 160)], "sync", "")
    d.arrow([(754, 160), (778, 160), (778, 110), (802, 110)], "proposed", "promote")
    # ops lane
    d.zone(14, 292, 1012, 136, "Operations — responsibilities and evidence", "gov", dash=None, sw=0.9)
    ops = [("Migrations", "separate step before rollout; never on container start; drift guard; up/down/up verified", "VERIFIED"),
           ("Secrets & config", "env vars; production config guards refuse unsafe defaults", "PARTIAL"),
           ("Monitoring", "metrics endpoints + readiness; no scrape / alert stack in repo", "PARTIAL"),
           ("Backup", "provider snapshots; RPO / RTO targets documented, not evidenced", "VERIFY"),
           ("Restore", "pg_restore + alembic check + smoke test runbook", "DESIGNED"),
           ("Rollback", "image rollback; migration downgrade caveat at 0047", "DESIGNED"),
           ("Incident response", "runbook + hypercare service; on-call not defined", "PARTIAL")]
    for i, (t, s, st) in enumerate(ops):
        x = 28 + i * 142
        d.box(x, 312, 134, 104, t, None, "gov", st, note=s, tsize=11.5, nsize=9.2)
    d.text(14, 22, "D13 · DEPLOYMENT & OPERATIONS", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1026, 22, "HYBRID · HOSTING REPORTED, NOT VERIFIED", 9, 500, C["slate"], "end", "mono", ls=1.2)
    return d


# ================================================================== D14 scenarios (sequence diagrams)
def seq(title, tag, parts, steps, w=1040, step=23, dark=False):
    n = len(parts)
    left, right = 20, w - 20
    colw = (right - left) / n
    xs = [left + colw * (i + 0.5) for i in range(n)]
    top = 40
    hh = 46
    nsteps = sum(1 for s in steps if s[0] != "frame_end")
    h = top + hh + 14 + nsteps * step + 6
    d = Diagram(w, int(h), dark=dark, title=title)
    for i, (name, sub, k) in enumerate(parts):
        bw = min(colw - 10, 132)
        d.box(xs[i] - bw / 2, top, bw, hh, name, sub, k, tsize=10.8, ssize=7.0, center=True, accent_side="top")
        d.line(xs[i], top + hh, xs[i], h - 12, C["slate2"], 1, "3 4")
    y = top + hh + 26
    k = 0
    frames = []
    for s in steps:
        if s[0] == "frame":
            frames.append((y - 14, s[1], s[2]))
            continue
        if s[0] == "frame_end":
            fy, lab, kind = frames.pop()
            col = C["coral"] if kind == "fail" else C["amberd"]
            d.rect(24, fy, w - 48, y - fy - 10, fill="none", stroke=col, sw=1, rx=6, dash="5 3")
            d.rect(24, fy, text_width(lab.upper(), 8, "mono", 500) + 22, 15, fill=col, rx=4)
            d.text(32, fy + 11, lab.upper(), 8, 500, C["white"], face="mono", ls=0.6)
            continue
        if s[0] == "note":
            _, i, txt, kind = s
            tw = min(text_width(txt, 9, "cond", 500) + 16, colw * 2.2)
            d.rect(xs[i] - tw / 2, y - 11, tw, 20, fill=KIND[kind][1], stroke=KIND[kind][0], sw=0.8, rx=4)
            d.text(xs[i], y + 3, txt, 9, 500, C["ink"], "middle")
            y += step
            continue
        a, b, lab, kind = s
        k += 1
        if a == b:
            d.arrow([(xs[a], y - 6), (xs[a] + 26, y - 6), (xs[a] + 26, y + 6), (xs[a] + 4, y + 6)], kind, r=4)
            if xs[a] + 32 + text_width(lab, 9.2, "cond", 500) > w - 10:
                tw = text_width(lab, 9.2, "cond", 500)
                d.rect(xs[a] - 26 - tw - 4, y - 8, tw + 8, 13, fill=C["paper"], rx=2)
                d.text(xs[a] - 26, y + 3, lab, 9.2, 500, C["ink"], "end")
            else:
                d.text(xs[a] + 32, y + 3, lab, 9.2, 500, C["ink"])
        else:
            d.arrow([(xs[a], y), (xs[b] + (-4 if b > a else 4), y)], kind)
            mx = (xs[a] + xs[b]) / 2
            d.rect(mx - text_width(lab, 9.2, "cond", 500) / 2 - 4, y - 15, text_width(lab, 9.2, "cond", 500) + 8, 12, fill=C["paper"], rx=2)
            d.text(mx, y - 5.5, lab, 9.2, 500, C["ink"], "middle")
        d.circle(xs[a] - 12 if b >= a else xs[a] + 12, y, 7, fill=C["navy"])
        d.text(xs[a] - 12 if b >= a else xs[a] + 12, y + 3, str(k), 7.6, 600, C["white"], "middle", "sans")
        y += step
    d.text(20, 22, title.upper(), 9, 500, C["slate"], face="mono", ls=1.3)
    d.text(w - 20, 22, tag, 9, 500, C["teal"], "end", "mono", ls=1.2)
    return d


def d14a_drone():
    parts = [("Drone + gateway", "MAVLink · uplink", "user"), ("Listener / ingest", "UDP · HTTP", "infra"), ("Job worker", "acquisition.ingest", "data"),
             ("Telemetry svc", "quality · map", "data"), ("HUMS", "features · limits", "domain"), ("M7", "signals", "decision"),
             ("LISA", "tools", "ai"), ("Maintainer", "authorised user", "user"), ("MRO", "work order", "domain")]
    steps = [(0, 1, "frames (signed)", "async"), (1, 2, "enqueue job (idempotency key)", "async"), (2, 3, "process_normalized_event", "sync"),
             (3, 3, "dedupe · quality gate · asset map", "sync"), (3, 4, "readings (SAVEPOINT)", "sync"),
             (4, 4, "feature > limit → exceedance (advisory lock)", "sync"), ("note", 4, "Finding + Evidence (reading ids)", "decision"),
             (7, 5, "GET signals → sync", "sync"), (5, 5, "signal_key dedupe → OPEN", "sync"), (7, 6, "“why is UAV-04 flagged?”", "sync"),
             (6, 5, "get_asset_proactive_signals (authz)", "sync"), (6, 7, "grounded explanation + tools cited", "sync"),
             (7, 5, "acknowledge → in review (audited)", "human"), (7, 8, "create work order from finding", "human"),
             ("frame", "failure paths", "fail"), (1, 1, "unsigned / unknown source → drop + counter", "sync"), (3, 3, "unknown asset → QUARANTINED, replay later", "sync"),
             (2, 2, "handler error → retry · backoff · dead-letter", "sync"), ("frame_end",)]
    return seq("D14·1 Drone telemetry anomaly → human-reviewed maintenance", "VERIFIED PATH", parts, steps)


def d14b_compliance():
    parts = [("Engineer", "rule author", "user"), ("Regulatory", "requirement", "ext"), ("Applicability", "Kleene engine", "domain"),
             ("Asset registry", "as-of config", "infra"), ("Obligations", "compliance", "decision"), ("Evidence", "files · review", "gov"),
             ("M7", "evidence gap", "decision"), ("Reviewer", "authorised user", "user"), ("Audit", "immutable", "gov")]
    steps = [(0, 1, "record AD + rule (condition tree)", "sync"), (1, 2, "evaluate for aircraft", "sync"), (2, 3, "as-of configuration", "sync"),
             (2, 2, "TRUE / FALSE / UNKNOWN + trace + snapshot", "sync"), (2, 4, "applicable → obligation (due, action)", "data"),
             (4, 5, "evidence requirements", "sync"), (6, 4, "missing evidence → COMPLIANCE_EVIDENCE_GAP", "sync"),
             (7, 5, "upload file (checksum) → SUBMITTED", "human"), (7, 5, "accept / reject with reason", "human"), (5, 4, "obligation → COMPLIANT", "sync"),
             (4, 8, "obligation sync · evidence events", "data"),
             ("frame", "failure & uncertainty", "fail"), (2, 2, "UNKNOWN → REVIEW_REQUIRED, never NOT_APPLICABLE", "sync"),
             (5, 5, "rejected evidence → obligation stays DUE / OVERDUE", "sync"), ("note", 6, "LISA may explain; it may not mark compliant", "risk"), ("frame_end",)]
    return seq("D14·2 Aircraft compliance obligation → evidence → authorised review", "VERIFIED · ADR-005 LINEAGE DESIGNED", parts, steps)


def d14c_subscription():
    parts = [("Platform admin", "platform:manage", "gov"), ("Catalogue", "suite · plan", "gov"), ("Provisioning", "factory", "infra"),
             ("Subscription", "lifecycle", "gov"), ("Resolver", "entitlements", "decision"), ("Org admin · user", "roles", "user"),
             ("Frontend", "nav · guard", "infra"), ("REST / LISA", "gates", "infra"), ("Worker", "async paths", "data")]
    steps = [(0, 1, "create HELICOPTER plan (features, limits)", "sync"), (0, 2, "provision organisation", "sync"),
             (2, 3, "subscription: plan in same suite", "sync"), (3, 3, "suite_plan_mismatch refused", "sync"),
             (5, 6, "login (JWT: identity + roles only)", "sync"), (6, 4, "GET /entitlements", "sync"), (4, 6, "modules · pages · features · limits", "sync"),
             (6, 6, "sidebar = route guard (display only)", "sync"), (5, 7, "POST /airframes", "sync"), (7, 4, "require_feature + RBAC", "sync"),
             (7, 5, "201 or 403 SUITE_ENTITLEMENT_REQUIRED", "sync"),
             ("frame", "lifecycle & failure paths", "fail"), (3, 3, "payment failed → PAST_DUE (grace) → cancel (opt-in)", "sync"),
             (7, 7, "next request after cancel → 403 (no stale token)", "sync"), (8, 8, "GAP F3: ingest continues until source paused", "prohibited"), ("frame_end",)]
    return seq("D14·3 Suite-specific subscription → effective features and permissions", "VERIFIED (+ GAP F3)", parts, steps)


# ================================================================== X1 event & integration architecture
def x01_events():
    d = Diagram(1040, 470, title="X01 Event and integration architecture")
    d.zone(14, 46, 470, 256, "One database transaction", "data", dash=None, sw=1.1)
    d.box(30, 66, 440, 54, "Domain mutation", "service function · e.g. work_order_service.transition_work_order", "domain", "VERIFIED", tsize=11.5)
    d.box(30, 150, 140, 60, "Domain row", "work_orders, findings…", "data", "VERIFIED", tsize=11, ssize=7.2)
    d.box(184, 150, 140, 60, "audit_events", "action · entity · metadata", "gov", "VERIFIED", tsize=11, ssize=7.2)
    d.box(338, 150, 132, 60, "background_jobs", "type · dedupe_key", "data", "VERIFIED", tsize=11, ssize=7.2)
    d.box(30, 234, 440, 56, "Proposed additions (ADR-012)", "event_version · correlation_id column · consumer_cursors table", "decision", "PROPOSED", tsize=11, ssize=7.4)
    for xx in (100, 254, 404):
        d.arrow([(xx, 120), (xx, 150)], "data")
    d.pill(250, 135, "commit = all or nothing (outbox-equivalent)", 8.4, C["white"], C["teal"], C["teal"])
    # consumers
    d.zone(520, 46, 506, 250, "Consumers (after commit)", "domain", dash=None, sw=1.1)
    cons = [("Worker", "claims jobs: ingest, poll, retention, dunning", "VERIFIED"), ("Developer-2 consumers", "poll audit_events by action (documented contract)", "VERIFIED"),
            ("M7 sync", "reads domain rows on request (F6)", "PARTIAL"), ("Exports · hypercare", "tenant export, audit list", "VERIFIED"),
            ("Webhook out / notifications", "no outbound event delivery", "PROPOSED")]
    for i, (t, s, st) in enumerate(cons):
        y = 64 + i * 45
        d.chip(536, y, 474, 38, t, s, "domain" if st == "VERIFIED" else ("decision" if st == "PARTIAL" else "ai"), st, 10.8, 7.4)
    d.arrow([(470, 180), (506, 180), (506, 83), (536, 83)], "async", "SKIP LOCKED", lpos=(506, 140))
    d.arrow([(254, 210), (254, 222), (494, 222), (494, 128), (536, 128)], "async", "poll", lpos=(400, 222))
    # catalogue
    d.rect(14, 316, 1012, 140, fill=C["white"], stroke=C["line"], rx=10)
    d.text(30, 338, "EVENT CATALOGUE IN USE (action strings verified in code)", 8.6, 600, C["slate"], face="mono", ls=1.2)
    cat = [("Missions", "mission.created · updated · authorized"), ("Findings", "finding.created · disposition_added · closed"),
           ("Work orders", "work_order.created · updated · assigned · transitioned"), ("Tasks", "task.created · updated · completed"),
           ("Configuration", "component / battery .installed · .removed"), ("Inspections", "inspection.completed · rejected · reopened"),
           ("Signals", "M7 lifecycle transitions (audited)"), ("Jobs", "acquisition.ingest · .poll · retention.sweep · billing.dunning")]
    for i, (k, v) in enumerate(cat):
        x = 30 + (i % 2) * 500
        y = 360 + (i // 2) * 22
        d.text(x, y, k, 10, 600, C["ink"])
        d.text(x + 104, y, v, 9, 400, C["slate"], face="mono")
    d.text(14, 22, "X01 · EVENT & INTEGRATION ARCHITECTURE — NO BROKER BY DESIGN", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1026, 22, "HYBRID", 9, 500, C["slate"], "end", "mono", ls=1.2)
    return d


# ================================================================== X2 traceability lineage
def x02_lineage():
    d = Diagram(1040, 230, title="X02 Traceability lineage")
    chain = [("Packet", "source_event_id", "data"), ("Event log", "event log row", "data"), ("Reading", "reading row", "data"),
             ("Feature", "hums_features", "domain"), ("Exceedance", "reading ids", "decision"), ("Finding", "finding_id", "decision"),
             ("Evidence", "provenance json", "gov"), ("Signal", "signal_key", "decision"), ("Work order", "work_order_id", "domain"), ("Audit", "audit_events", "gov")]
    w, g = 92, 11
    for i, (t, s, k) in enumerate(chain):
        x = 14 + i * (w + g)
        d.box(x, 56, w, 62, t, s, k, tsize=11, ssize=6.8, center=True, accent_side="top")
        if i < len(chain) - 1:
            d.arrow([(x + w, 87), (x + w + g, 87)], "sync" if i not in (7,) else "human")
    d.rect(14, 136, 1012, 80, fill=C["white"], stroke=C["line"], rx=8)
    d.mtext(30, 158, "Verified links: packet → event log → reading → exceedance (contributing reading ids) → finding → evidence (provenance). "
            "Signal ↔ work order is a human action; the link is held in metadata, not a foreign key. Proposed (roadmap 4): one correlation id carried from "
            "packet to closed work order, and an outcome field on the work order that feeds HUMS baselines.", 990, 10, 400, C["ink"], lh=1.4)
    d.text(14, 22, "X02 · OBSERVATION → FINDING → DECISION → EVIDENCE → ACTION", 9, 500, C["slate"], face="mono", ls=1.4)
    d.text(1026, 22, "PARTIAL — END-TO-END ID PROPOSED", 9, 500, C["amberd"], "end", "mono", ls=1.2)
    return d


# ================================================================== X3 roadmap
def x03_roadmap():
    from model import ROADMAP
    d = Diagram(1040, 560, title="X03 Dependency-aware technical roadmap")
    waves = [("WAVE 1 · FOUNDATIONS", 250, 500), ("WAVE 2 · INTEGRITY & OPERATIONS", 510, 760), ("WAVE 3 · INTELLIGENCE", 770, 1026)]
    for lab, x0, x1 in waves:
        d.rect(x0, 40, x1 - x0, 506, fill=C["white"], stroke=C["line"], rx=8)
        d.text(x0 + 10, 58, lab, 8.4, 600, C["slate"], face="mono", ls=1.2)
    wave_of = {1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 1, 7: 2, 8: 2}
    kinds = {1: "data", 2: "gov", 3: "risk", 4: "decision", 5: "decision", 6: "infra", 7: "ai", 8: "domain"}
    ys = {}
    for i, r in enumerate(ROADMAP):
        y = 72 + i * 59
        ys[r["n"]] = y
        d.rect(14, y, 226, 50, fill=KIND[kinds[r["n"]]][1], rx=6)
        d.text(28, y + 31, str(r["n"]), 20, 700, KIND[kinds[r["n"]]][0], face="disp")
        d.mtext(52, y + 20, r["title"], 180, 10.8, 600, C["ink"], lh=1.15)
        w = wave_of[r["n"]]
        x0 = waves[w][1] + 8
        x1 = waves[w][2] - 8
        if r["n"] in (3, 6):
            x1 = waves[1][2] - 8
        d.rect(x0, y + 4, x1 - x0, 42, fill=KIND[kinds[r["n"]]][1], stroke=KIND[kinds[r["n"]]][0], sw=1, rx=5)
        dep = "" if r["dep"] == "—" else f"after {r['dep']}"
        off = 0
        if dep:
            off = d.pill(x0 + 8, y + 15, dep, 8, C["white"], KIND[kinds[r["n"]]][0], KIND[kinds[r["n"]]][0], anchor="start") + 6
        d.mtext(x0 + 8 + off, y + 18, r["items"][0], x1 - x0 - 44 - off, 9, 600, C["ink"], lh=1.2, max_lines=1)
        d.mtext(x0 + 8, y + 36, r["gate"], x1 - x0 - 44, 8.4, 400, C["slate"], lh=1.2, max_lines=1)
        gx = x1 - 14
        d.raw(f'<path d="M{gx},{y+15} L{gx+8},{y+25} L{gx},{y+35} L{gx-8},{y+25} Z" fill="{C["amber"]}" stroke="{C["amberd"]}"/>')
    d.text(14, 22, "X03 · ROADMAP — ORDER BY DEPENDENCY, NOT BY DATE", 9, 500, C["slate"], face="mono", ls=1.4)
    d.raw(f'<path d="M820,14 L828,22 L820,30 L812,22 Z" fill="{C["amber"]}" stroke="{C["amberd"]}"/>')
    d.text(834, 26, "exit gate (evidence)", 9, 500, C["slate"])

    return d



# ================================================================== X4 connectivity decision tree
def x04_tree():
    d = Diagram(1040, 190, title="X04 Connectivity decision tree")
    qs = [("Does the OEM cloud expose telemetry?", 20), ("Can the airframe carry a companion computer + modem?", 270), ("Is there a radio-linked ground station?", 520), ("Does the autopilot write logs?", 770)]
    outs = [("A · Connected-aircraft service", "VERIFIED"), ("Companion computer (live)", "PARTIAL"), ("B · Ground relay (live in range)", "EXTERNAL"), ("D · Post-flight sync", "PROPOSED")]
    for i, ((q, x), (o, st)) in enumerate(zip(qs, outs)):
        d.rect(x, 20, 230, 50, fill="#FDF4E1", stroke=C["amberd"], rx=25)
        d.mtext(x + 115, 41, q, 200, 10, 600, C["ink"], anchor="middle", lh=1.2)
        d.arrow([(x + 115, 70), (x + 115, 112)], "sync", "yes", lpos=(x + 115, 90))
        d.box(x + 10, 112, 210, 46, o, None, "domain", st, tsize=11)
        if i < 3:
            d.arrow([(x + 230, 45), (qs[i + 1][1], 45)], "sync", "no", lpos=(x + 240, 45))
    d.arrow([(1000, 45), (1020, 45), (1020, 176), (980, 176)], "sync", "no")
    d.text(975, 180, "E · Manual import (fallback)", 10, 600, C["ink"], "end")
    return d
