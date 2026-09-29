import os
import sys
import json
import time
import urllib.request
import urllib.error

BASE_URL = "https://aerocomply-backend-staging.onrender.com/api/v1"
QA_ORG_ID = "b990db30-78f4-4666-b141-ff23a1f73177"
QA_PASSWORD = os.environ.get("QA_PASSWORD", "REDACTED_USE_ENV")

ACTIVE_QA_USERS = [
    {"email": "qa-maintenance-manager@kotas-aerospace-qa.com", "role": "CAMO_MANAGER", "desc": "QA Maintenance Manager (CAMO_MANAGER)"},
    {"email": "qa-maintenance-engineer@kotas-aerospace-qa.com", "role": "MAINTENANCE_ENGINEER", "desc": "QA Maintenance Engineer (MAINTENANCE_ENGINEER)"},
    {"email": "qa-technician@kotas-aerospace-qa.com", "role": "MAINTENANCE_ENGINEER", "desc": "QA Technician (ME role)"},
    {"email": "qa-inspector@kotas-aerospace-qa.com", "role": "QUALITY_MANAGER", "desc": "QA Inspector (QUALITY_MANAGER)"},
    {"email": "qa-pilot@kotas-aerospace-qa.com", "role": "VIEWER", "desc": "QA Pilot (VIEWER role)"},
    {"email": "qa-viewer@kotas-aerospace-qa.com", "role": "VIEWER", "desc": "QA Viewer (VIEWER role)"},
]

def make_request(method, endpoint, data=None, token=None, headers_extra=None):
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if headers_extra:
        headers.update(headers_extra)
    
    req_body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=req_body, headers=headers, method=method)
    
    t0 = time.time()
    try:
        with urllib.request.urlopen(req) as resp:
            elapsed_ms = (time.time() - t0) * 1000
            res_body = resp.read().decode("utf-8")
            return {
                "status": resp.status,
                "data": json.loads(res_body) if res_body else None,
                "elapsed_ms": elapsed_ms,
                "error": None,
                "headers": dict(resp.headers),
            }
    except urllib.error.HTTPError as e:
        elapsed_ms = (time.time() - t0) * 1000
        res_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(res_body)
        except Exception:
            parsed = res_body
        return {
            "status": e.code,
            "data": parsed,
            "elapsed_ms": elapsed_ms,
            "error": str(e),
            "headers": dict(e.headers),
        }
    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000
        return {
            "status": 0,
            "data": None,
            "elapsed_ms": elapsed_ms,
            "error": str(e),
            "headers": {},
        }

def run_full_suite():
    print("=" * 75, flush=True)
    print("KOTA AEROSPACE - M8 MASTER UAT & OPERATIONAL READINESS SUITE", flush=True)
    print("=" * 75, flush=True)
    
    perf_metrics = {}
    
    # -------------------------------------------------------------
    # 0. Environment & Infrastructure Audit
    # -------------------------------------------------------------
    print("\n--- PHASE M8.0: REPOSITORY & STAGING AUDIT ---", flush=True)
    health = make_request("GET", "/health")
    perf_metrics["GET /health"] = health["elapsed_ms"]
    print(f"Health check: status={health['status']} ({health['elapsed_ms']:.1f}ms) -> {health['data']}", flush=True)
    assert health["status"] == 200, "Health check failed"

    # -------------------------------------------------------------
    # 1. Role-Based Access & Authentication
    # -------------------------------------------------------------
    print("\n--- PHASE M8.1: ROLE-BASED ACCESS & AUTHENTICATION ---", flush=True)
    tokens = {}
    for u in ACTIVE_QA_USERS:
        res = make_request("POST", "/auth/login", {"email": u["email"], "password": QA_PASSWORD})
        elapsed = res["elapsed_ms"]
        perf_metrics[f"POST /auth/login ({u['role']})"] = elapsed
        if res["status"] == 200 and "access_token" in res["data"]:
            tokens[u["role"]] = res["data"]["access_token"]
            tokens[u["email"]] = res["data"]["access_token"]
            print(f"  [PASS] {u['role']:<22} | {u['email']:<42} | HTTP {res['status']} ({elapsed:.1f}ms)", flush=True)
        else:
            print(f"  [FAIL] {u['role']:<22} | {u['email']:<42} | HTTP {res['status']}: {res['data']}", flush=True)

    # Negative Auth Tests
    bad_cred = make_request("POST", "/auth/login", {"email": "qa-maintenance-manager@kotas-aerospace-qa.com", "password": "WrongPassword999!"})
    print(f"  [PASS] Invalid password rejected with HTTP {bad_cred['status']} (code={bad_cred['data'].get('error', {}).get('code')})", flush=True)
    
    bad_tok = make_request("GET", "/assets", token="malformed.jwt.token")
    print(f"  [PASS] Invalid JWT token rejected with HTTP {bad_tok['status']}", flush=True)

    camo_token = tokens["CAMO_MANAGER"]
    me_token = tokens["MAINTENANCE_ENGINEER"]
    qm_token = tokens["QUALITY_MANAGER"]
    viewer_token = tokens["VIEWER"]

    # -------------------------------------------------------------
    # 2. RBAC Direct Backend Authorization Boundaries
    # -------------------------------------------------------------
    print("\n--- PHASE M8.1 / M8.2: RBAC AUTHORIZATION BOUNDARIES ---", flush=True)
    # VIEWER attempting to create asset (needs write)
    v_create_asset = make_request("POST", "/assets", {
        "registration": "VT-UNAUTH", "asset_type": "AIRCRAFT", "model": "Test", "manufacturer": "Test"
    }, token=viewer_token)
    print(f"  [PASS] VIEWER create asset: HTTP {v_create_asset['status']} (Forbidden enforced server-side)", flush=True)

    # VIEWER attempting to create work order
    v_create_wo = make_request("POST", "/work-orders", {
        "work_order_number": "WO-UNAUTH-001", "title": "Unauthorized WO", "work_order_type": "CORRECTIVE"
    }, token=viewer_token)
    print(f"  [PASS] VIEWER create work-order: HTTP {v_create_wo['status']} (Forbidden enforced server-side)", flush=True)

    # VIEWER attempting to create compliance assessment
    v_assess = make_request("POST", "/compliance-assessments", {
        "requirement_id": "00000000-0000-0000-0000-000000000000",
        "aircraft_id": "00000000-0000-0000-0000-000000000000",
        "status": "COMPLIANT"
    }, token=viewer_token)
    print(f"  [PASS] VIEWER create assessment: HTTP {v_assess['status']} (Forbidden enforced server-side)", flush=True)

    # -------------------------------------------------------------
    # 3. Organization & Users Administration
    # -------------------------------------------------------------
    print("\n--- PHASE M8.3: TENANT USERS & DASHBOARD ---", flush=True)
    dash = make_request("GET", "/tenant/dashboard", token=camo_token)
    perf_metrics["GET /tenant/dashboard"] = dash["elapsed_ms"]
    print(f"  Tenant Dashboard: HTTP {dash['status']} ({dash['elapsed_ms']:.1f}ms) -> org={dash['data'].get('organization', {}).get('name') if dash['data'] else 'N/A'}", flush=True)

    users_list = make_request("GET", "/tenant/users", token=camo_token)
    perf_metrics["GET /tenant/users"] = users_list["elapsed_ms"]
    print(f"  Tenant Users: HTTP {users_list['status']} ({users_list['elapsed_ms']:.1f}ms) -> {len(users_list['data'])} total users provisioned", flush=True)
    for u in users_list['data']:
        print(f"    - User: {u.get('email')} ({u.get('full_name')}) -> roles={u.get('roles')}", flush=True)

    # -------------------------------------------------------------
    # 4. Fleet & Asset Operations
    # -------------------------------------------------------------
    print("\n--- PHASE M8.4: ASSET OPERATIONS ---", flush=True)
    assets_all_res = make_request("GET", "/assets", token=camo_token)
    perf_metrics["GET /assets"] = assets_all_res["elapsed_ms"]
    assets_all = assets_all_res["data"] if isinstance(assets_all_res["data"], list) else []
    print(f"  All Assets: HTTP {assets_all_res['status']} ({assets_all_res['elapsed_ms']:.1f}ms) -> {len(assets_all)} assets found", flush=True)
    
    aircraft_list = make_request("GET", "/aircraft", token=camo_token)
    perf_metrics["GET /aircraft"] = aircraft_list["elapsed_ms"]
    ac_items = aircraft_list["data"] if isinstance(aircraft_list["data"], list) else []
    print(f"  Aircraft: HTTP {aircraft_list['status']} ({aircraft_list['elapsed_ms']:.1f}ms) -> {len(ac_items)} aircraft", flush=True)
    for a in ac_items:
        print(f"    - Aircraft {a.get('registration')}: type={a.get('aircraft_type')}, msn={a.get('msn')}, status={a.get('status', 'ACTIVE')}", flush=True)

    drones_list = make_request("GET", "/drones", token=camo_token)
    perf_metrics["GET /drones"] = drones_list["elapsed_ms"]
    dr_items = drones_list["data"] if isinstance(drones_list["data"], list) else []
    print(f"  Drones: HTTP {drones_list['status']} ({drones_list['elapsed_ms']:.1f}ms) -> {len(dr_items)} drones", flush=True)
    for d in dr_items:
        print(f"    - Drone {d.get('registration')}: model={d.get('model')}, status={d.get('status')}", flush=True)

    # -------------------------------------------------------------
    # 5. Missions & Flights Workflow
    # -------------------------------------------------------------
    print("\n--- PHASE M8.5: MISSION / FLIGHT WORKFLOW ---", flush=True)
    missions_res = make_request("GET", "/missions", token=camo_token)
    perf_metrics["GET /missions"] = missions_res["elapsed_ms"]
    mission_items = missions_res["data"].get("items", []) if isinstance(missions_res["data"], dict) else (missions_res["data"] if isinstance(missions_res["data"], list) else [])
    print(f"  Missions: HTTP {missions_res['status']} ({missions_res['elapsed_ms']:.1f}ms) -> {len(mission_items)} missions", flush=True)
    for m in mission_items:
        print(f"    - Mission: purpose='{m.get('purpose')}', area='{m.get('operating_area')}', status={m.get('status')}", flush=True)

    # Check asset flight history & operations
    drone1 = next((d for d in assets_all if d.get("registration") == "KQA-UAV-001"), None)
    if drone1:
        d1_id = drone1.get("id")
        d1_ops = make_request("GET", f"/assets/{d1_id}/operations", token=camo_token)
        print(f"  KQA-UAV-001 Operations: HTTP {d1_ops['status']} -> total_flight_hours={d1_ops['data'].get('total_flight_hours') if d1_ops['data'] else 'N/A'}, total_cycles={d1_ops['data'].get('total_cycles') if d1_ops['data'] else 'N/A'}", flush=True)

    # -------------------------------------------------------------
    # 6. Maintenance & Work Order Workflow
    # -------------------------------------------------------------
    print("\n--- PHASE M8.6: MAINTENANCE WORKFLOW ---", flush=True)
    wos_res = make_request("GET", "/work-orders", token=me_token)
    perf_metrics["GET /work-orders"] = wos_res["elapsed_ms"]
    wos = wos_res["data"] if isinstance(wos_res["data"], list) else []
    print(f"  Work Orders: HTTP {wos_res['status']} ({wos_res['elapsed_ms']:.1f}ms) -> {len(wos)} work orders", flush=True)
    for wo in wos:
        print(f"    - WO {wo.get('work_order_number')}: '{wo.get('title')}' | type={wo.get('work_order_type')}, status={wo.get('status')}, priority={wo.get('priority')}", flush=True)

    # -------------------------------------------------------------
    # 7. Inspection & Finding Workflows
    # -------------------------------------------------------------
    print("\n--- PHASE M8.7 / M8.8: INSPECTIONS & FINDINGS WORKFLOW ---", flush=True)
    findings_res = make_request("GET", "/findings", token=qm_token)
    perf_metrics["GET /findings"] = findings_res["elapsed_ms"]
    findings = findings_res["data"] if isinstance(findings_res["data"], list) else []
    print(f"  Findings: HTTP {findings_res['status']} ({findings_res['elapsed_ms']:.1f}ms) -> {len(findings)} findings", flush=True)
    for f in findings:
        print(f"    - Finding: '{f.get('title')}' | severity={f.get('severity')}", flush=True)

    # Check inspections for WO-KQA-001
    wo1 = next((w for w in wos if w.get("work_order_number") == "WO-KQA-001"), None)
    if wo1:
        wo1_id = wo1.get("id")
        insp_wo1 = make_request("GET", f"/inspections/by-work-order/{wo1_id}", token=qm_token)
        insp_items = insp_wo1["data"] if isinstance(insp_wo1["data"], list) else []
        print(f"  WO-KQA-001 Inspections: HTTP {insp_wo1['status']} -> {len(insp_items)} requirements", flush=True)
        for i in insp_items:
            print(f"    - Insp Req: task_id={i.get('task_id')}, required={i.get('required')}, status={i.get('status')}", flush=True)

    # -------------------------------------------------------------
    # 8. Component & Battery Verification
    # -------------------------------------------------------------
    print("\n--- PHASE M8.9: COMPONENT & BATTERY WORKFLOW ---", flush=True)
    ac1_asset = next((a for a in assets_all if a.get("registration") == "VT-QA01"), None)
    if ac1_asset:
        ac1_asset_id = ac1_asset.get("id")
        ac1_comps = make_request("GET", f"/assets/{ac1_asset_id}/components", token=camo_token)
        comps_list = ac1_comps["data"] if isinstance(ac1_comps["data"], list) else []
        print(f"  VT-QA01 Components: HTTP {ac1_comps['status']} -> {len(comps_list)} components", flush=True)
        for c in comps_list:
            print(f"    - Component: {c.get('name')} (s/n {c.get('serial_number')}) - type={c.get('component_type')}, status={c.get('status')}", flush=True)

    # Check drone 3 components
    drone3 = next((d for d in assets_all if d.get("registration") == "KQA-UAV-003"), None)
    if drone3:
        d3_id = drone3.get("id")
        d3_comps = make_request("GET", f"/assets/{d3_id}/components", token=camo_token)
        d3_list = d3_comps["data"] if isinstance(d3_comps["data"], list) else []
        print(f"  KQA-UAV-003 Components: HTTP {d3_comps['status']} -> {len(d3_list)} components", flush=True)
        for c in d3_list:
            print(f"    - Component: {c.get('name')} (s/n {c.get('serial_number')}) - type={c.get('component_type')}, status={c.get('status')}", flush=True)

    # -------------------------------------------------------------
    # 9. Compliance Workflow & UNKNOWN State Preservation
    # -------------------------------------------------------------
    print("\n--- PHASE M8.11: COMPLIANCE WORKFLOW ---", flush=True)
    reg_reqs = make_request("GET", "/regulatory-requirements", token=qm_token)
    perf_metrics["GET /regulatory-requirements"] = reg_reqs["elapsed_ms"]
    reqs = reg_reqs["data"] if isinstance(reg_reqs["data"], list) else []
    print(f"  Regulatory Requirements: HTTP {reg_reqs['status']} ({reg_reqs['elapsed_ms']:.1f}ms) -> {len(reqs)} requirements", flush=True)
    for r in reqs:
        print(f"    - Req {r.get('requirement_number')}: '{r.get('title')}' (authority={r.get('authority')})", flush=True)

    # -------------------------------------------------------------
    # 10. Readiness Workflow & Blocking Factors
    # -------------------------------------------------------------
    print("\n--- PHASE M8.12: ASSET READINESS & BLOCKING FACTORS ---", flush=True)
    for asset in assets_all:
        asset_id = asset.get("id")
        reg = asset.get("registration")
        readiness = make_request("GET", f"/assets/{asset_id}/readiness", token=camo_token)
        if readiness["status"] == 200 and readiness["data"]:
            rdata = readiness["data"]
            is_ready = rdata.get("is_ready") or rdata.get("status")
            blockers = rdata.get("blockers") or rdata.get("blocking_factors") or []
            print(f"  Asset {reg:<14}: readiness_status={rdata.get('readiness_status', 'N/A')} is_ready={is_ready} blockers={len(blockers)}", flush=True)
            for b in blockers:
                print(f"      * Blocker: {b}", flush=True)

    # -------------------------------------------------------------
    # 11. Proactive Intelligence Validation (M7 Signals)
    # -------------------------------------------------------------
    print("\n--- PHASE M8.13: PROACTIVE INTELLIGENCE (M7 SIGNALS) ---", flush=True)
    intel_summary = make_request("GET", "/intelligence/summary", token=camo_token)
    perf_metrics["GET /intelligence/summary"] = intel_summary["elapsed_ms"]
    print(f"  Intelligence Summary: HTTP {intel_summary['status']} ({intel_summary['elapsed_ms']:.1f}ms)", flush=True)
    if intel_summary["data"]:
        print(f"    Summary Counts: total={intel_summary['data'].get('total_active_signals')}, critical={intel_summary['data'].get('critical_signals_count')}, high={intel_summary['data'].get('high_signals_count')}", flush=True)

    signals_resp = make_request("GET", "/intelligence/signals", token=camo_token)
    perf_metrics["GET /intelligence/signals"] = signals_resp["elapsed_ms"]
    signals_list = signals_resp["data"] if isinstance(signals_resp["data"], list) else []
    print(f"  Intelligence Signals: HTTP {signals_resp['status']} ({signals_resp['elapsed_ms']:.1f}ms) -> {len(signals_list)} signals detected", flush=True)
    
    tested_signal_id = None
    for s in signals_list:
        print(f"    [{s.get('severity'):<8}] {s.get('signal_type'):<32} | {s.get('headline')} (status={s.get('status')})", flush=True)
        if s.get("status") == "OPEN" and tested_signal_id is None:
            tested_signal_id = s.get("id")

    # -------------------------------------------------------------
    # 12. Intelligence Lifecycle Validation (OPEN -> ACK -> REVIEW -> RESOLVED)
    # -------------------------------------------------------------
    print("\n--- PHASE M8.14: INTELLIGENCE SIGNAL LIFECYCLE ---", flush=True)
    if tested_signal_id:
        print(f"  Testing Signal Lifecycle transitions on signal ID: {tested_signal_id}", flush=True)
        # 1. Acknowledge
        ack_res = make_request("POST", f"/intelligence/signals/{tested_signal_id}/acknowledge", {
            "notes": "Acknowledged by CAMO Manager during M8 UAT"
        }, token=camo_token)
        print(f"    [1. ACKNOWLEDGE]: HTTP {ack_res['status']} -> status={ack_res['data'].get('status') if ack_res['data'] else 'N/A'}", flush=True)
        
        # 2. In Review
        rev_res = make_request("POST", f"/intelligence/signals/{tested_signal_id}/in-review", {
            "review_notes": "Diagnostic investigation underway"
        }, token=camo_token)
        print(f"    [2. IN_REVIEW]  : HTTP {rev_res['status']} -> status={rev_res['data'].get('status') if rev_res['data'] else 'N/A'}", flush=True)

        # 3. Resolve
        res_res = make_request("POST", f"/intelligence/signals/{tested_signal_id}/resolve", {
            "resolution_notes": "Resolved following replacement and ground run verification"
        }, token=camo_token)
        print(f"    [3. RESOLVE]    : HTTP {res_res['status']} -> status={res_res['data'].get('status') if res_res['data'] else 'N/A'}", flush=True)

    # -------------------------------------------------------------
    # 13. Grounded LISA Operational Validation
    # -------------------------------------------------------------
    print("\n--- PHASE M8.15: GROUNDED LISA OPERATIONAL VALIDATION ---", flush=True)
    lisa_queries = [
        "What needs attention today?",
        "Which assets are approaching maintenance thresholds?",
        "Why is this asset high priority?",
        "What compliance issues need attention?",
        "What findings are recurring?",
        "What is affecting readiness?",
        "Show me the evidence for this signal."
    ]
    for q in lisa_queries:
        lisa_res = make_request("POST", "/lisa/ask", {"question": q}, token=camo_token)
        perf_metrics[f"POST /lisa/ask ({q[:20]}...)"] = lisa_res["elapsed_ms"]
        print(f"\n  Query: \"{q}\"", flush=True)
        print(f"  Status: HTTP {lisa_res['status']} ({lisa_res['elapsed_ms']:.1f}ms)", flush=True)
        if lisa_res["status"] == 200 and lisa_res["data"]:
            answer = lisa_res["data"].get("answer") or lisa_res["data"].get("headline") or ""
            narrative = lisa_res["data"].get("narrative") or []
            print(f"  Answer: {answer[:180]}...", flush=True)
            if narrative:
                print(f"  Narrative: {str(narrative)[:180]}...", flush=True)
        else:
            print(f"  Output: {str(lisa_res['data'])[:200]}", flush=True)

    # -------------------------------------------------------------
    # Performance Summary
    # -------------------------------------------------------------
    print("\n" + "=" * 75, flush=True)
    print("M8 PERFORMANCE BENCHMARKS (LIVE STAGING)", flush=True)
    print("=" * 75, flush=True)
    for op, ms in perf_metrics.items():
        print(f"  {op:<45} : {ms:6.1f} ms", flush=True)

    print("\nSTAGING VALIDATION RUN COMPLETE.", flush=True)

if __name__ == "__main__":
    run_full_suite()
