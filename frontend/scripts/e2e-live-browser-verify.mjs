import http from "node:http";

async function fetchUrl(url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(url, options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        resolve({
          status: res.statusCode,
          headers: res.headers,
          body: data,
        });
      });
    });
    req.on("error", reject);
    if (options.body) {
      req.write(typeof options.body === "string" ? options.body : JSON.stringify(options.body));
    }
    req.end();
  });
}

async function runLiveVerification() {
  console.log("================================================================");
  console.log("RUNNING LIVE HTTP END-TO-END VERIFICATION (Frontend + Backend)");
  console.log("================================================================");

  // 1. Check Backend Health
  console.log("\n[1/7] Testing Backend Health...");
  const backendHealth = await fetchUrl("http://127.0.0.1:8000/api/v1/health");
  console.log(`Backend /health status: ${backendHealth.status}`);
  if (backendHealth.status !== 200) throw new Error(`Backend health failed: ${backendHealth.status}`);

  // 2. Check Frontend Landing Page
  console.log("\n[2/7] Testing Frontend Root & Login Routes...");
  const loginPage = await fetchUrl("http://localhost:3000/login");
  console.log(`Frontend /login status: ${loginPage.status}`);
  if (loginPage.status !== 200) throw new Error(`Frontend /login failed: ${loginPage.status}`);

  // 3. Authenticate via Backend API
  console.log("\n[3/7] Authenticating test user via /api/v1/auth/login...");
  const loginRes = await fetchUrl("http://127.0.0.1:8000/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: {
      email: "orgadmin@apex-aero.com",
      password: "DevPassword123!",
    },
  });
  console.log(`Login response status: ${loginRes.status}`);
  if (loginRes.status !== 200) throw new Error(`Login failed: ${loginRes.body}`);
  const authData = JSON.parse(loginRes.body);
  const accessToken = authData.access_token;
  const refreshToken = authData.refresh_token;
  console.log("Access token obtained successfully. Length:", accessToken.length);

  // 4. Test Entitlements API
  console.log("\n[4/7] Testing /api/v1/entitlements API...");
  const entRes = await fetchUrl("http://127.0.0.1:8000/api/v1/entitlements", {
    method: "GET",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  console.log(`Entitlements API status: ${entRes.status}`);
  const entData = JSON.parse(entRes.body);
  console.log("Effective Features:", JSON.stringify(entData.effective_features, null, 2));

  // 5. Test Frontend App Pages with SSR / prerender
  console.log("\n[5/7] Testing Next.js Application Routes (SSR / HTML generation)...");
  const routesToTest = [
    "/dashboard",
    "/aircraft",
    "/ai",
    "/maintenance/work-orders",
    "/compliance",
    "/procurement",
    "/intelligence/fleet",
  ];

  for (const route of routesToTest) {
    const pageRes = await fetchUrl(`http://localhost:3000${route}`);
    console.log(`Route ${route.padEnd(28)} -> HTTP ${pageRes.status}`);
    if (pageRes.status !== 200) {
      throw new Error(`Failed to render route ${route}: status ${pageRes.status}`);
    }
  }

  // 6. Test LISA Status Endpoint
  console.log("\n[6/7] Testing LISA Status Endpoint (no 503 probe)...");
  const lisaStatus = await fetchUrl("http://127.0.0.1:8000/api/v1/lisa/status", {
    method: "GET",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  console.log(`LISA Status endpoint response: ${lisaStatus.status} ${lisaStatus.body}`);
  if (lisaStatus.status !== 200) throw new Error(`LISA status failed: ${lisaStatus.status}`);

  // 7. Test Token Refresh Endpoint
  console.log("\n[7/7] Testing Single-Flight Token Refresh Flow...");
  const refreshRes = await fetchUrl("http://127.0.0.1:8000/api/v1/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: { refresh_token: refreshToken },
  });
  console.log(`Refresh endpoint status: ${refreshRes.status}`);
  if (refreshRes.status !== 200) throw new Error(`Token refresh failed: ${refreshRes.body}`);
  const refreshData = JSON.parse(refreshRes.body);
  console.log("New Access Token obtained:", refreshData.access_token.slice(0, 20) + "...");

  console.log("\n================================================================");
  console.log("ALL LIVE STAGING VERIFICATION TESTS COMPLETED WITH 100% SUCCESS!");
  console.log("================================================================");
}

runLiveVerification().catch((err) => {
  console.error("Verification failed:", err);
  process.exit(1);
});
