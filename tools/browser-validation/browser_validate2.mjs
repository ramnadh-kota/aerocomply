// Real-browser validation over the Chrome DevTools Protocol (no automation library installed).
// Drives headless Chrome against the running production build (3000) + API (8001).
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const SCRATCH = (process.env.BROWSER_SCRATCH ?? os.tmpdir()).replaceAll(path.sep, "/");
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
  const API = "http://localhost:8001/api/v1";
  const apiStatus = (p) => ev(`fetch('${API}${p}',{headers:{Authorization:'Bearer '+localStorage.getItem('aerocomply_access_token')}}).then(r=>r.status)`);
  const navLinks = () => ev("[...document.querySelectorAll('nav a')].map(a=>({t:a.innerText.replace(/[^\\x20-\\x7E]/g,'').trim(), disabled:a.getAttribute('aria-disabled')==='true'}))");

  // ================= drone organisation: strict sidebar, live vs mock-only pages
  await loginAs("browser-drone@example.com");
  await visit("/dashboard");
  const links = await navLinks();
  const find = (t) => links.find((l) => l.t.toLowerCase().includes(t));
  note("nav", "Drones link enabled for the drone suite", !!find("drones") && !find("drones").disabled, JSON.stringify(find("drones")));
  note("nav", "Helicopters / eVTOL / Aircraft links are locked for a drone-suite org", ["helicopters", "evtol", "aircraft"].every((t) => find(t) && find(t).disabled), JSON.stringify(["helicopters", "evtol", "aircraft"].map(find)));
  note("nav", "a mock-only module (Finance is not in nav; Pilot Workflow) is locked in a live session", !!find("pilot workflow") && find("pilot workflow").disabled);

  await visit("/helicopters", { expectBlocked: true, shotName: "heli_blocked_for_drone_org" });
  await visit("/evtols", { expectBlocked: true });
  note("security", "drone org: GET /helicopters is 403 (API)", (await apiStatus("/helicopters")) === 403);
  const fin = await visit("/finance", { shotName: "finance_not_connected" });
  note("ui", "mock-only /finance shows the 'not connected' notice, not sample data", /not connected to live data/i.test(fin.body) && !/\$\s?\d{2,}/.test(fin.body.slice(0, 400)), fin.body.slice(0, 120).replace(/\s+/g, " "));
  await visit("/engines", { expectText: "Not connected to live data" });
  await visit("/organization/usage", { expectText: "Not connected to live data" });
  const ev1 = await visit("/evidence", { shotName: "evidence_live" });
  note("live", "/evidence renders the live register (table or empty state), never sample rows", /Evidence/.test(ev1.body) && !/Not connected/.test(ev1.body) && /(No evidence has been recorded|Title)/i.test(ev1.body), ev1.body.slice(0, 100).replace(/\s+/g, " "));
  for (const p of ["/procurement", "/procurement/parts", "/procurement/vendors", "/procurement/approvals", "/regulations", "/assessments", "/notifications", "/maintenance/defects"]) {
    const r = await visit(p);
    note("live", `${p} is a connected page`, !/Not connected to live data/.test(r.body), r.body.slice(0, 80).replace(/\s+/g, " "));
  }

  // ================= helicopter organisation: full UI journey
  await loginAs("browser-heli@example.com");
  await visit("/dashboard");
  const hl = await navLinks();
  const hf = (t) => hl.find((l) => l.t.toLowerCase().includes(t));
  note("nav", "helicopter org: Helicopters enabled, Drones / eVTOL locked", hf("helicopters") && !hf("helicopters").disabled && hf("drones")?.disabled && hf("evtol")?.disabled, JSON.stringify([hf("helicopters"), hf("drones"), hf("evtol")]));
  await visit("/drones", { expectBlocked: true });
  await visit("/evtols", { expectBlocked: true });
  note("security", "helicopter org: GET /drones and /evtols are 403 (API)", (await apiStatus("/drones")) === 403 && (await apiStatus("/evtols")) === 403);

  await go("/helicopters");
  const REG = "HB" + String(Date.now()).slice(-6);
  await setValue("input[aria-label=Registration]", REG);
  await setValue("input[aria-label=Manufacturer]", "Airbus");
  await setValue("input[aria-label=Model]", "H145");
  await setValue("select[aria-label='Rotor system']", "SINGLE_MAIN_TAIL");
  await setValue("input[aria-label='Main rotor blades']", "4");
  await setValue("input[aria-label=Engines]", "2");
  await clickText("create helicopter", "button");
  await until(async () => (await text()).includes(REG), 10000);
  note("helicopter-ui", "create a helicopter from the UI and see it listed", (await text()).includes(REG));
  await shot("heli_list");

  // invalid detail is rejected client-side with a clear message
  await setValue("input[aria-label=Registration]", "BAD-1");
  await setValue("input[aria-label=Engines]", "9");
  await clickText("create helicopter", "button");
  await sleep(600);
  note("helicopter-ui", "out-of-range engine count is refused with an inline message", /out of range/i.test(await text()));

  // open detail
  await ev(`(()=>{const a=[...document.querySelectorAll('a')].find(x=>x.innerText.trim()===${JSON.stringify(REG)}); if(a) a.click();})()`);
  await until(async () => /Airframe details/.test(await text()), 10000);
  note("helicopter-ui", "detail page opens", /Airframe details/.test(await text()) && (await path_()).startsWith("/helicopters/"));
  await setValue("input[aria-label='Flight minutes']", "75");
  await setValue("input[aria-label=Cycles]", "2");
  await clickText("record flight", "button");
  await until(async () => /1 flights/.test(await text()), 8000);
  note("helicopter-ui", "record a flight -> utilization shows 1 flight, 1.3 h, 2 cycles", /1 flights · 1\.3 h · 2 cycles/.test(await text()), (await text()).match(/\d+ flights[^\n]*/)?.[0] ?? "");
  await setValue("select[aria-label='Component type']", "ROTOR");
  await setValue("input[aria-label='Component name']", "Main rotor head");
  await clickText("add component", "button");
  await until(async () => /Main rotor head/.test(await text()), 8000);
  note("helicopter-ui", "add a component and see it listed", /Main rotor head/.test(await text()));
  await clickText("apply hums starter template", "button");
  await until(async () => /HUMS template applied: 6 created/.test(await text()), 8000);
  note("helicopter-ui", "apply the HUMS starter template (6 sensors)", /HUMS template applied: 6 created, 0 already present/.test(await text()), (await text()).match(/HUMS template applied[^\n]*/)?.[0] ?? "");
  await clickText("apply hums starter template", "button");
  await until(async () => /0 created, 6 already present/.test(await text()), 8000);
  note("helicopter-ui", "applying the template again is idempotent", /0 created, 6 already present/.test(await text()));
  await shot("heli_detail");

  // ================= eVTOL organisation
  await loginAs("browser-evtol@example.com");
  await visit("/helicopters", { expectBlocked: true });
  await go("/evtols");
  const EV = "EB" + String(Date.now()).slice(-6);
  await setValue("input[aria-label=Registration]", EV);
  await setValue("select[aria-label=Configuration]", "LIFT_CRUISE");
  await setValue("input[aria-label=Propulsors]", "4");
  await clickText("create evtol", "button");
  await until(async () => (await text()).includes(EV), 10000);
  note("evtol-ui", "create an eVTOL from the UI and see it listed", (await text()).includes(EV));
  await ev(`(()=>{const a=[...document.querySelectorAll('a')].find(x=>x.innerText.trim()===${JSON.stringify(EV)}); if(a) a.click();})()`);
  await until(async () => /Battery packs/.test(await text()), 10000);
  note("evtol-ui", "eVTOL detail shows the battery section (battery_analytics entitled)", /Battery packs/.test(await text()));
  await setValue("input[aria-label='Battery serial']", "HVB-" + Date.now());
  await clickText("attach", "button");
  await until(async () => /Battery attached\./.test(await text()), 8000);
  note("evtol-ui", "attach a battery pack", /Battery attached\./.test(await text()));
  await clickText("apply hums starter template", "button");
  await until(async () => /HUMS template applied: 9 created/.test(await text()), 8000);
  note("evtol-ui", "eVTOL HUMS template scales with propulsor count (4 + 5 = 9)", /HUMS template applied: 9 created/.test(await text()), (await text()).match(/HUMS template applied[^\n]*/)?.[0] ?? "");
  await shot("evtol_detail");
} catch (e) {
  note("harness", "script error", false, String(e && e.stack || e).slice(0, 500));
} finally {
  fs.writeFileSync(`${SCRATCH}/browser_results2.json`, JSON.stringify({ results, visits }, null, 1));
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  const allConsoleErrors = visits.flatMap((v) => v.console.filter((c) => c.startsWith("error")).map((c) => `${v.label}: ${c}`));
  const allNet = visits.flatMap((v) => v.net.map((n) => `${v.label}: ${n}`));
  console.log(`console errors: ${allConsoleErrors.length}; failed HTTP responses (>=400): ${allNet.length}`);
  if (allConsoleErrors.length) console.log(allConsoleErrors.slice(0, 8).join("\n"));
  if (allNet.length) console.log(allNet.slice(0, 8).join("\n"));
  ws.close(); chrome.kill();
  process.exit(failed.length ? 1 : 0);
}
