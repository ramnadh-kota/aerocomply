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
  const MOCK = /Aero India|Meridian Airlines|Continental CAMO|WO-10[4-9]\d|VT-[A-Z]{3}\b|N7\d{2}[A-Z]{2}\b/;
  const pages = ["/dashboard", "/maintenance/control-center", "/maintenance/control-tower", "/maintenance/hangar", "/maintenance/operations",
    "/maintenance/work-orders", "/maintenance/inspections", "/maintenance/technicians", "/maintenance/deferred", "/maintenance/parts",
    "/compliance", "/compliance/regulatory-register", "/assets", "/drones", "/tenant/dashboard", "/tenant/fleet", "/tenant/audit",
    "/procurement/purchase-orders", "/intelligence/fleet", "/facilities"];
  await loginAs("browser-drone@example.com");
  const cc = await (async () => { await go("/maintenance/control-center"); return ev("(document.querySelector('main')||document.body).innerText"); })();
  note("live", "control center renders live summary tiles and the drone fleet", /Open work orders/.test(cc) && /BRW-001/.test(cc) && !MOCK.test(cc), cc.slice(0, 120).replace(/\s+/g, " "));
  await go("/maintenance/control-tower");
  await sleep(1500);
  note("redirect", "control tower (sample sections) sends a live session to the live control center", (await path_()) === "/maintenance/control-center", await path_());
  for (const who of ["browser-drone@example.com", "aircraft-admin@example.com"]) {
    await loginAs(who);
    for (const p of pages) {
      await go(p);
      const body = await ev("(document.querySelector('main')||document.body).innerText");
      const hit = body.match(MOCK);
      note("mock-leak", `${who.split("@")[0]} ${p}`, !hit, hit ? `MOCK MARKER "${hit[0]}" in: ${body.slice(Math.max(0, hit.index - 60), hit.index + 60).replace(/\s+/g, " ")}` : "");
    }
  }
} catch (e) {
  note("harness", "script error", false, String(e && e.stack || e).slice(0, 500));
} finally {
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  ws.close(); chrome.kill();
  process.exit(failed.length ? 1 : 0);
}
