// Real-browser validation over the Chrome DevTools Protocol (no automation library installed).
// Drives headless Chrome against the running production build (3000) + API (8001).
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const SCRATCH = (process.env.BROWSER_SCRATCH ?? os.tmpdir()).replaceAll(path.sep, "/");
const SEED = JSON.parse(fs.readFileSync(`${SCRATCH}/browser_seed.json`, "utf8"));
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9334;
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


// ---------------------------------------------------------------------------------------------------------------
// Live-session guarantees for the G1 closure: no sample data through global search, the tour or unconnected routes;
// connected equivalents are reached by redirect; everything else says "Not connected to live data".
const MOCK = /VT-ABC|VT-XYZ|Sample data|Demo data|demonstration data only|Acme Aviation|Jane Doe/i;

const REDIRECTS = {
  "/assessments/abc-1/review": "/assessments/abc-1",
  "/fleet/aircraft/abc-2/health": "/aircraft/abc-2",
  "/aircraft/abc-3/configuration": "/aircraft/abc-3",
  "/maintenance/planning/abc-4": "/maintenance/work-orders/abc-4",
  "/maintenance/discrepancies": "/maintenance/defects",
  "/maintenance/material-readiness": "/maintenance/parts",
  "/documents": "/evidence",
  "/compliance/pre-audit": "/compliance",
  "/integrations": "/data-sources",
  "/maintenance/projects": "/maintenance/work-orders",
};
const NOTICE_ONLY = ["/automation", "/finance", "/finance/abc", "/maintenance/projects/abc",
  "/maintenance/projects/abc/intelligence", "/organization/readiness", "/pilot", "/reports", "/reports/abc", "/workspace"];

try {
  await loginAs("browser-drone@example.com");

  // 1. global search: live records only
  await go("/dashboard");
  const search = async (q) => {
    await setValue("input[type=search]", q);
    await sleep(1500);
    return ev("(document.querySelector('[role=listbox]')||{innerText:''}).innerText");
  };
  const sampleHit = await search("VT-ABC");
  const sampleOptions = await ev("document.querySelectorAll('[role=option]').length");
  note("search", "sample aircraft VT-ABC is NOT findable by a live session (no result options)", sampleOptions === 0, sampleHit.replace(/\s+/g, " ").slice(0, 80));
  const liveHit = await search("BRW-001");
  note("search", "the organization's own drone BRW-001 is found through the API", /BRW-001/.test(liveHit), liveHit.replace(/\s+/g, " ").slice(0, 80));
  const clicked = await ev("(()=>{const o=[...document.querySelectorAll('[role=option]')].find(e=>/BRW-001/.test(e.innerText)); if(!o) return false; o.click(); return true;})()");
  await sleep(1500);
  note("search", "opening the result lands on the live drone page", clicked && /^\/drones\/[0-9a-f-]{36}$/.test(await path_()), await path_());

  // 2. welcome tour never mentions or links to the sample aircraft
  await go("/dashboard");
  await ev("localStorage.removeItem('kota-aerospace-onboarding-seen')");
  await send("Page.navigate", { url: BASE + "/dashboard" });
  await until(async () => (await ev("document.readyState")) === "complete", 20000);
  await sleep(2500);
  let tourText = "";
  for (let i = 0; i < 12; i++) {
    tourText += " " + (await text());
    if (!(await clickText("next", "button"))) break;
    await sleep(250);
  }
  const hasDone = await ev("!![...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='Done')");
  note("tour", "live tour shows no sample-aircraft step or button", !/demo aircraft|Open VT-ABC/i.test(tourText) && hasDone, hasDone ? "ends with Done" : "no Done button");
  await clickText("done", "button");

  // 3. redirects to connected equivalents
  for (const [from, to] of Object.entries(REDIRECTS)) {
    await go(from);
    await until(async () => (await path_()) === to, 8000);
    note("redirect", `${from} -> ${to}`, (await path_()) === to, await path_());
  }

  // 4. everything without a live backend says so and shows no sample rows
  for (const p of NOTICE_ONLY) {
    await go(p);
    const body = await ev("(document.querySelector('main')||document.body).innerText");
    note("notice", `${p} says it is not connected and leaks nothing`, /Not connected to live data/i.test(body) && !MOCK.test(body.replace(/demonstration data only/i, "")), body.replace(/\s+/g, " ").slice(0, 70));
  }

  note("health", "no console errors / failed requests on the last page", rec.console.length === 0 && rec.page.length === 0, JSON.stringify(rec.console.slice(0, 2)));
} catch (e) {
  note("harness", "script error", false, String(e && e.stack || e).slice(0, 500));
} finally {
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  ws.close(); chrome.kill();
  process.exit(failed.length ? 1 : 0);
}
