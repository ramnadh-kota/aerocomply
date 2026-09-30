// Real-browser validation over the Chrome DevTools Protocol (no automation library installed).
// Drives headless Chrome against the running production build (3000) + API (8001).
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const SCRATCH = process.env.BROWSER_SCRATCH ?? os.tmpdir().replace(/\/g, "/");
const SEED = JSON.parse(fs.readFileSync(`${SCRATCH}/browser_seed.json`, "utf8"));
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9333;
const BASE = "http://localhost:3000";
const PW = "M20Preview!123";
const SRC_NAME = "Browser CSV " + Date.now();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const userDir = fs.mkdtempSync(path.join(os.tmpdir(), "kota-chrome-"));
const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${userDir}`, "--window-size=1440,1000", "about:blank",
], { stdio: "ignore" });

async function until(fn, ms = 15000, step = 200) {
  const t0 = Date.now();
  for (;;) {
    try { const v = await fn(); if (v) return v; } catch { /* retry */ }
    if (Date.now() - t0 > ms) return null;
    await sleep(step);
  }
}

await until(async () => (await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok, 20000);
const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

let nextId = 1; const pending = new Map(); const listeners = [];
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { const { res, rej } = pending.get(msg.id); pending.delete(msg.id); msg.error ? rej(new Error(msg.error.message)) : res(msg.result); }
  else if (msg.method) listeners.forEach((l) => l(msg));
};
const send = (method, params = {}) => new Promise((res, rej) => { const id = nextId++; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });

// ---- evidence collection
let rec = { console: [], page: [], net: [], failed: [] };
const reqs = new Map();
listeners.push((msg) => {
  const p = msg.params;
  if (msg.method === "Runtime.consoleAPICalled" && (p.type === "error" || p.type === "warning")) {
    rec.console.push(`${p.type}: ${(p.args || []).map((a) => a.value ?? a.description ?? a.type).join(" ").slice(0, 300)}`);
  } else if (msg.method === "Runtime.exceptionThrown") {
    rec.page.push((p.exceptionDetails.exception?.description || p.exceptionDetails.text || "exception").slice(0, 300));
  } else if (msg.method === "Network.requestWillBeSent") {
    reqs.set(p.requestId, `${p.request.method} ${p.request.url}`);
  } else if (msg.method === "Network.responseReceived" && p.response.status >= 400) {
    rec.net.push(`${p.response.status} ${reqs.get(p.requestId) ?? p.response.url}`);
  } else if (msg.method === "Network.loadingFailed" && p.errorText !== "net::ERR_ABORTED") {
    rec.failed.push(`${p.errorText} ${reqs.get(p.requestId) ?? ""}`);
  }
});
for (const d of ["Page", "Runtime", "Network", "Log", "DOM"]) await send(`${d}.enable`);

const ev = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result?.value;
const text = () => ev("document.body ? document.body.innerText : ''");
const path_ = () => ev("location.pathname");
async function dismissTour() {
  for (let i = 0; i < 3; i++) {
    const shown = await ev("!!([...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='Skip') && /welcome tour/i.test(document.body.innerText))");
    if (!shown) return;
    await clickText("skip", "button");
    await sleep(500);
  }
}
async function go(url) {
  rec = { console: [], page: [], net: [], failed: [] };
  await send("Page.navigate", { url: url.startsWith("http") ? url : BASE + url });
  await until(async () => (await ev("document.readyState")) === "complete", 20000);
  await sleep(2200);
  await dismissTour();
}
async function shot(name) {
  const { data } = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(`${SCRATCH}/shot_${name}.png`, Buffer.from(data, "base64"));
}
async function setValue(sel, v) {
  return ev(`(()=>{const el=document.querySelector(${JSON.stringify(sel)}); if(!el) return false;
    const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto,'value').set.call(el, ${JSON.stringify(v)});
    el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true})); return true;})()`);
}
const clickText = (t, tag = "button,a,[role=button]") => ev(`(()=>{const el=[...document.querySelectorAll(${JSON.stringify(tag)})].find(e=>e.innerText&&e.innerText.trim().toLowerCase().includes(${JSON.stringify(t.toLowerCase())})); if(!el) return false; el.click(); return true;})()`);

const results = [];
const note = (area, name, ok, detail = "") => { results.push({ area, name, ok, detail }); console.log(`${ok ? "PASS" : "FAIL"}  [${area}] ${name}${detail ? " — " + detail : ""}`); };
const ERROR_MARKERS = /application error|something went wrong|unhandled runtime error|this page could not be found|internal server error/i;

// Console noise we consider expected for deliberate negative tests is asserted per-scenario, not ignored globally.
function visitReport(label, extra = {}) {
  return { label, console: [...rec.console], page: [...rec.page], net: [...rec.net], failed: [...rec.failed], ...extra };
}
const visits = [];

async function loginAs(email, password = PW) {
  await go("/login");
  await ev("localStorage.clear(); sessionStorage.clear();");
  await go("/login");
  await setValue("input[type=email]", email);
  await setValue("input[type=password]", password);
  await clickText("sign in", "button");
  if (!(await clickText("log in", "button"))) { /* submit already triggered by first click if label matched */ }
  return until(async () => (await path_()) !== "/login", 15000);
}

async function visit(pathname, { expectText, expectBlocked, shotName } = {}) {
  await go(pathname);
  const body = await text();
  const where = await path_();
  const v = visitReport(pathname, { landed: where, chars: body.length });
  visits.push(v);
  const broken = ERROR_MARKERS.test(body);
  const okText = expectText ? body.toLowerCase().includes(expectText.toLowerCase()) : true;
  const blocked = expectBlocked ? /not included|entitlement required|not authorized|not entitled|forbidden|access denied|locked/i.test(body) : true;
  const errs = [...v.page, ...v.console.filter((c) => c.startsWith("error"))];
  note("browser", `${pathname}${expectBlocked ? " (must be blocked)" : ""}`, !broken && okText && blocked && v.page.length === 0,
    `landed=${where}${expectText && !okText ? ` missing "${expectText}"` : ""}${expectBlocked && !blocked ? " NOT BLOCKED" : ""}` +
    `${v.net.length ? ` net=${JSON.stringify(v.net.slice(0, 3))}` : ""}${errs.length ? ` errors=${JSON.stringify(errs.slice(0, 2))}` : ""}`);
  if (shotName) await shot(shotName);
  return { body, v };
}

try {
  // 1. unauthenticated protection
  await go("/dashboard");
  await ev("localStorage.clear()");
  await go("/dashboard");
  note("auth", "unauthenticated /dashboard redirects to /login", (await path_()).startsWith("/login"), await path_());

  // 2. wrong password
  await go("/login");
  await setValue("input[type=email]", "browser-drone@example.com");
  await setValue("input[type=password]", "definitely-wrong-password");
  await ev("document.querySelector('form button[type=submit]').click()");
  await sleep(2500);
  const wrongBody = (await text()).toLowerCase();
  note("auth", "wrong password stays on /login and shows an error", (await path_()) === "/login" && /invalid|incorrect|failed|wrong|unable|error/.test(wrongBody), wrongBody.slice(0, 120).replace(/\n/g, " "));
  await shot("login_error");

  // 3. real login (drone org admin)
  await go("/login");
  await setValue("input[type=email]", "browser-drone@example.com");
  await setValue("input[type=password]", PW);
  await ev("document.querySelector('form button[type=submit]').click()");
  const left = await until(async () => (await path_()) !== "/login", 15000);
  note("auth", "valid login leaves /login", !!left, await path_());
  const tokenStored = await ev("!!(localStorage.getItem('aerocomply_access_token'))");
  note("auth", "session token persisted", !!tokenStored);

  // 4. drone organisation: pages that must work
  const A = SEED.assets["BRW-001"];
  await visit("/dashboard", { shotName: "dashboard" });
  const dashBody = await text();
  note("ui", "topbar shows the REAL organization and no prototype selectors / mock orgs", /Browser Drone Co/.test(dashBody) && !/Aero India/.test(dashBody) && !(await ev("!!document.querySelector('select[aria-label*=Organization]')")), (dashBody.match(/Organization.{0,40}/)?.[0] ?? ""));
  await visit("/drones", { expectText: "BRW-001", shotName: "drones" });
  const assetsVisit = await visit("/assets", { expectText: "BRW-001" });
  note("navigation", "Fleet Registry has no broken link (previously /import -> 404)", !assetsVisit.v.net.some((n) => /localhost:3000\/import/.test(n)), JSON.stringify(assetsVisit.v.net.slice(0, 2)));
  await go(`/assets/${A}`);
  await clickText("intelligence", "button");
  await sleep(3000);
  const asset = await visit(`/assets/${A}?tab=INTELLIGENCE`, { shotName: "asset_telemetry" });
  note("telemetry", "asset page shows the telemetry panel with the ingested sensor", /VIB_MAIN_SYS1/.test(asset.body) && /Telemetry/.test(asset.body), asset.body.match(/VIB_MAIN_SYS1[^\n]{0,60}/)?.[0] ?? "no sensor row");
  note("hums", "asset page shows HUMS section", /HUMS/.test(asset.body));
  await visit("/data-sources", { expectText: "MAVLink gateway", shotName: "data_sources" });
  await visit("/tenant/subscription");
  await visit("/tenant/entitlements");
  await visit("/tenant/usage");
  await visit("/intelligence/fleet");
  await visit("/maintenance/work-orders");
  await visit("/ai");

  // 5. cross-suite protection (drone org must not reach aircraft)
  const acr = await visit("/aircraft", { expectBlocked: true, shotName: "aircraft_blocked" });
  await visit("/aircraft/00000000-0000-0000-0000-000000000000", { expectBlocked: true });
  const apiCode = await ev(`fetch('http://localhost:8001/api/v1/aircraft',{headers:{Authorization:'Bearer '+localStorage.getItem('aerocomply_access_token')}}).then(r=>r.status)`);
  note("security", "drone org: GET /api/v1/aircraft is 403 from the real browser session", apiCode === 403, String(apiCode));
  const navText = await ev("[...document.querySelectorAll('nav a, aside a')].map(a=>a.innerText.trim()).filter(Boolean).join('|')");
  note("navigation", "sidebar does not offer Platform administration to an org user", !/Organizations|Product Catalog|Provisioning/.test(navText.replace(/Facilities|Organization Settings/g, "")), navText.slice(0, 160));
  await visit("/platform/organizations", { expectBlocked: false });
  const platBody = await text();
  const platMain = await ev("(document.querySelector('main')||document.body).innerText");
  note("security", "org admin on /platform/organizations gets the Not-authorized card (platform page not mounted)", /not authorized/i.test(platMain) && !/Provisioning|Customer tenants control plane/i.test(platMain) && !rec.net.some((n) => /\/platform\/organizations/.test(n)), platMain.slice(0, 120).replace(/\s+/g, " "));

  // 6. Data Sources UI workflow
  await go("/data-sources");
  await setValue("form input[maxlength='128']", SRC_NAME);
  await setValue("form select", "CSV_BATCH");
  await clickText("register", "button");
  await sleep(500);
  await until(async () => (await text()).includes(SRC_NAME), 8000);
  note("data-sources", "register a source from the UI", (await text()).includes(SRC_NAME));
  // activate it
  const activated = await ev(`(()=>{const row=[...document.querySelectorAll('tr')].find(r=>r.innerText.includes(${JSON.stringify(SRC_NAME)})); if(!row) return false; const b=[...row.querySelectorAll('button')].find(x=>/activate/i.test(x.innerText)); if(!b) return false; b.click(); return true;})()`);
  await sleep(1500);
  const rowText = await ev(`(()=>{const row=[...document.querySelectorAll('tr')].find(r=>r.innerText.includes(${JSON.stringify(SRC_NAME)})); return row?row.innerText:''})()`);
  note("data-sources", "activate the source from the UI", activated && /ACTIVE/.test(rowText), rowText.replace(/\s+/g, " ").slice(0, 100));
  // select it and upload a CSV
  await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.innerText.trim()===${JSON.stringify(SRC_NAME)}); if(b) b.click();})()`);
  await sleep(800);
  const csvPath = `${SCRATCH.replace(/\//g, "\\")}\\upload_test.csv`;
  fs.writeFileSync(csvPath, `asset_id,sensor_code,value,unit,timestamp\nBRW-002,TEMP_ESC,41.5,C,${new Date(Date.now() - 60000).toISOString()}\nBRW-002,TEMP_ESC,42.5,C,${new Date(Date.now() - 30000).toISOString()}\nNOBODY-1,TEMP_ESC,1,C,${new Date().toISOString()}\n`);
  const { root } = await send("DOM.getDocument");
  const { nodeId } = await send("DOM.querySelector", { nodeId: root.nodeId, selector: "input[type=file]" });
  if (nodeId) {
    await send("DOM.setFileInputFiles", { files: [csvPath], nodeId });
    await until(async () => /received \d+/i.test(await text()), 10000);
    const rep = (await text()).match(/Received \d+:[^\n]+/)?.[0] ?? "";
    note("data-sources", "upload a CSV: 2 accepted, 1 quarantined (unknown asset)", /accepted 2/.test(rep) && /quarantined 1/.test(rep), rep);
    await shot("data_sources_ingest");
  } else note("data-sources", "file input available for CSV source", false, "no file input");
  // health after ingestion
  await go("/data-sources");
  await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.innerText.trim()===${JSON.stringify(SRC_NAME)}); if(b) b.click();})()`);
  await sleep(1000);
  const healthText = await text();
  note("data-sources", "health evidence shown for the source", /Last success|Events accepted/.test(healthText) && /Quarantined/.test(healthText));

  // 7. LISA
  await go("/ai");
  const filled = await setValue("textarea, input[type=text]", `What is the telemetry status of BRW-001?`);
  await clickText("send", "button") || await clickText("ask", "button");
  await sleep(4000);
  const lisaBody = await text();
  note("lisa", "LISA page accepts a question and renders a response or a clear not-configured state", filled && /BRW-001|not configured|telemetry|unable|error/i.test(lisaBody), lisaBody.slice(-200).replace(/\n/g, " "));
  await shot("lisa");

  // 8. logout
  await clickText("browser drone admin", "header button");
  await sleep(600);
  const out2 = await clickText("sign out", "button");
  await sleep(2000);
  note("auth", "logout control found and returns to /login", !!out2 && (await path_()).startsWith("/login"), `${out2} -> ${await path_()}`);
  await go("/dashboard");
  note("auth", "after logout /dashboard requires login again", (await path_()).startsWith("/login"), await path_());

  // 9. expired / corrupted session
  await loginAs("browser-drone@example.com");
  await ev("localStorage.setItem('aerocomply_access_token','garbage.token.value'); localStorage.setItem('aerocomply_refresh_token','garbage.refresh.value');");
  await go("/dashboard");
  const expiredPath = await path_();
  const expiredBody = await text();
  note("auth", "corrupted/expired session is sent to /login (no crash)", expiredPath.startsWith("/login") && !ERROR_MARKERS.test(expiredBody) && rec.page.length === 0, `${expiredPath} pageErrors=${rec.page.length}`);

  // 10. platform administrator
  const pl = await loginAs("platform@example.com");
  note("platform", "platform admin login", !!pl, await path_());
  for (const p of ["/platform/dashboard", "/platform/organizations", "/platform/subscriptions", "/platform/plans", "/platform/product-catalog", "/platform/monitoring", "/platform/audit"]) await visit(p);
  await shot("platform_orgs");

  // 11. aircraft organisation sees the mirror image
  await loginAs("aircraft-admin@example.com");
  await visit("/aircraft", { expectText: "Aircraft", shotName: "aircraft_ok" });
  await visit("/drones", { expectBlocked: true });
  const acCode = await ev(`fetch('http://localhost:8001/api/v1/drones',{headers:{Authorization:'Bearer '+localStorage.getItem('aerocomply_access_token')}}).then(r=>r.status)`);
  note("security", "aircraft org: GET /api/v1/drones is 403 from the real browser session", acCode === 403, String(acCode));
} catch (e) {
  note("harness", "script error", false, String(e && e.stack || e).slice(0, 400));
} finally {
  fs.writeFileSync(`${SCRATCH}/browser_results.json`, JSON.stringify({ results, visits }, null, 1));
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  const allConsoleErrors = visits.flatMap((v) => v.console.filter((c) => c.startsWith("error")).map((c) => `${v.label}: ${c}`));
  const allNet = visits.flatMap((v) => v.net.map((n) => `${v.label}: ${n}`));
  console.log(`console errors: ${allConsoleErrors.length}; failed HTTP responses (>=400): ${allNet.length}; failed requests: ${visits.reduce((n, v) => n + v.failed.length, 0)}`);
  ws.close(); chrome.kill();
  process.exit(failed.length ? 1 : 0);
}
