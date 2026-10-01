// Real-browser validation over the Chrome DevTools Protocol (no automation library installed).
// Drives headless Chrome against the running production build (3000) + API (8001).
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const SCRATCH = (process.env.BROWSER_SCRATCH ?? os.tmpdir()).replaceAll(path.sep, "/");
const SEED = JSON.parse(fs.readFileSync(`${SCRATCH}/browser_seed.json`, "utf8"));
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9335;
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
// Exhaustive live-session leak scan: EVERY page route of the app (static + dynamic with sample ids), for two live
// organizations. Markers are extracted from the bundled sample-data modules themselves, so nothing is hand-picked.
const FRONTEND = path.resolve(import.meta.dirname, "../../frontend").replaceAll(path.sep, "/");
const APP = `${FRONTEND}/app/(app)`;
const MOCKDIR = `${FRONTEND}/lib/mock`;

function routes(dir, prefix = "") {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.isDirectory()) out.push(...routes(`${dir}/${e.name}`, `${prefix}/${e.name}`));
    else if (e.name === "page.tsx") out.push(prefix || "/");
  }
  return out;
}
const SAMPLE_IDS = ["ac-1", "wo-1", "eng-1", "cmp-1", "p-1", "abc-1", "1"];
const allRoutes = routes(APP).sort();

const markers = new Set();
for (const f of fs.readdirSync(MOCKDIR, { recursive: true }).filter((n) => String(n).endsWith(".ts") && !/(^|[\/])roles\.ts$/.test(String(n)))) {   // role names are real RBAC roles, not sample records
  const src = fs.readFileSync(`${MOCKDIR}/${f}`, "utf8");
  for (const re of [/workOrderNumber: "([^"]{5,})"/g, /registrationMark: "([^"]{4,})"/g, /registration: "([^"]{4,})"/g,
    /partNumber: "([^"]{5,})"/g, /name: "([A-Z][a-z]+ [A-Z][a-z]+)"/g, /name: "([^"]+\(demo\))"/g, /serialNumber: "([^"]{6,})"/g]) {
    for (const m of src.matchAll(re)) markers.add(m[1]);
  }
}
for (const generic of ["Meridian Airlines", "Aero India", "Continental CAMO", "Sample data", "Demo data"]) markers.add(generic);
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const MARKER_RE = new RegExp([...markers].map(esc).join("|"));
console.log(`routes: ${allRoutes.length}, sample-data markers: ${markers.size}`);

const concrete = (r) => r.includes("[") ? SAMPLE_IDS.map((id) => r.replace(/\[[^\]]+\]/g, id)) : [r];
try {
  for (const who of (process.env.WHO ?? "browser-drone@example.com,aircraft-admin@example.com").split(",")) {
    await loginAs(who);
    let visited = 0;
    const leaks = [];
    for (const r of allRoutes) {
      if (r.startsWith("/platform") || r.startsWith("/login") || r.startsWith("/(auth)")) continue;
      const urls = r.includes("[") ? concrete(r).slice(0, 2) : [r];   // two sample ids per dynamic route keeps the crawl bounded
      for (const u of urls) {
        await go(u);
        const body = await ev("(document.querySelector('main')||document.body).innerText");
        visited++;
        const hit = body.match(MARKER_RE);
        if (hit) leaks.push(`${u} -> "${hit[0]}": ${body.slice(Math.max(0, hit.index - 50), hit.index + 50).replace(/\s+/g, " ")}`);
        if (ERROR_MARKERS.test(body) && !/this page could not be found/i.test(body)) leaks.push(`${u} -> ERROR PAGE: ${body.slice(0, 80).replace(/\s+/g, " ")}`);
      }
    }
    note("leak-scan", `${who.split("@")[0]}: ${visited} page loads across ${allRoutes.length} routes show no sample-data marker and no crash`, leaks.length === 0, leaks.slice(0, 8).join(" || "));
  }
} catch (e) {
  note("harness", "script error", false, String(e && e.stack || e).slice(0, 500));
} finally {
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  ws.close(); chrome.kill();
  process.exit(failed.length ? 1 : 0);
}
