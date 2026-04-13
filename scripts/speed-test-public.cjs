/**
 * AMTTP Public Speed Test — Measures real latency through amttp.com (Cloudflare Tunnel)
 * Path: User → Cloudflare CDN → QUIC Tunnel → nginx Gateway → Microservice
 */
const https = require('https');
const http = require('http');

const BASE = 'https://amttp.com';
const LOCAL = 'http://127.0.0.1';

function measure(url, { method = 'GET', body = null, label = '' } = {}) {
  return new Promise((resolve) => {
    const mod = url.startsWith('https') ? https : http;
    const parsed = new URL(url);
    const opts = {
      hostname: parsed.hostname,
      port: parsed.port || (url.startsWith('https') ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method,
      headers: {},
      timeout: 20000,
    };
    if (body) {
      opts.headers['Content-Type'] = 'application/json';
      opts.headers['Content-Length'] = Buffer.byteLength(body);
    }

    const start = process.hrtime.bigint();
    let ttfb = 0;
    const req = mod.request(opts, (res) => {
      ttfb = Number(process.hrtime.bigint() - start) / 1e6;
      let data = '';
      res.on('data', (c) => (data += c));
      res.on('end', () => {
        const total = Number(process.hrtime.bigint() - start) / 1e6;
        resolve({ label, status: res.statusCode, ttfb, total, size: Buffer.byteLength(data) });
      });
    });
    req.on('error', (e) => {
      const total = Number(process.hrtime.bigint() - start) / 1e6;
      resolve({ label, status: 0, ttfb: total, total, size: 0, error: e.message });
    });
    req.on('timeout', () => {
      req.destroy();
      const total = Number(process.hrtime.bigint() - start) / 1e6;
      resolve({ label, status: 0, ttfb: total, total, size: 0, error: 'timeout' });
    });
    if (body) req.write(body);
    req.end();
  });
}

function fmt(r) {
  const icon = r.status === 200 ? '✅' : r.status === 422 ? '⚠️' : r.status === 0 ? '❌' : `⚠️`;
  const sizeStr = r.size > 0 ? `${(r.size / 1024).toFixed(1)}KB` : '-';
  return `  ${icon} ${r.label.padEnd(32)} TTFB: ${r.ttfb.toFixed(0).padStart(5)}ms  Total: ${r.total.toFixed(0).padStart(5)}ms  Size: ${sizeStr.padStart(8)}  [${r.status}]`;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const riskBody = JSON.stringify({
  transaction_id: 'bench-001',
  from_address: '0xdead0000000000000000000000000000deadbeef',
  to_address: '0xbeef0000000000000000000000000000deadbeef',
  value_eth: 1.5,
  chain_id: 1,
});
const sanctionsBody = JSON.stringify({
  address: '0xdead0000000000000000000000000000deadbeef',
});
const explainBody = JSON.stringify({
  address: '0xdead0000000000000000000000000000deadbeef',
  risk_score: 750,
});

async function run() {
  console.log('╔══════════════════════════════════════════════════════════════════╗');
  console.log('║  AMTTP PUBLIC SPEED TEST — https://amttp.com                    ║');
  console.log('║  Path: User → Cloudflare CDN → QUIC Tunnel → nginx → Service   ║');
  console.log('╚══════════════════════════════════════════════════════════════════╝\n');

  // Warmup TLS
  await measure(`${BASE}/health`, { label: 'warmup' });
  await sleep(200);

  // ── Section 1: Frontend Pages ──
  console.log('── FRONTEND PAGES ──');
  const frontend = [
    { url: `${BASE}/`, label: 'Landing Page (Next.js SSR)' },
    { url: `${BASE}/app/`, label: 'Flutter Login (static)' },
    { url: `${BASE}/war-room`, label: 'War Room Dashboard (SSR)' },
    { url: `${BASE}/app/main.dart.js`, label: 'Flutter JS Bundle (3.6MB)' },
    { url: `${BASE}/app/flutter.js`, label: 'Flutter Engine JS' },
    { url: `${BASE}/app/canvaskit/canvaskit.js`, label: 'CanvasKit WASM loader' },
  ];
  for (const t of frontend) {
    const r = await measure(t.url, { label: t.label });
    console.log(fmt(r));
    await sleep(100);
  }

  // ── Section 2: Data APIs ──
  console.log('\n── DATA APIs (Next.js → MongoDB: 920K transactions) ──');
  const dataApis = [
    { url: `${BASE}/api/health`, label: 'API Health' },
    { url: `${BASE}/api/data/stats`, label: 'Dashboard Stats (aggregation)' },
    { url: `${BASE}/api/data/flagged?limit=5`, label: 'Flagged Transactions (5)' },
    { url: `${BASE}/api/data/flagged?limit=50`, label: 'Flagged Transactions (50)' },
  ];
  for (const t of dataApis) {
    const r = await measure(t.url, { label: t.label });
    console.log(fmt(r));
    await sleep(100);
  }

  // ── Section 3: Microservice Health (gateway proxy) ──
  console.log('\n── MICROSERVICE HEALTH (Cloudflare → nginx → service) ──');
  const services = [
    { url: `${BASE}/risk/health`, label: 'Risk Engine (8000)' },
    { url: `${BASE}/sanctions/health`, label: 'Sanctions (8004)' },
    { url: `${BASE}/monitoring/health`, label: 'Monitoring (8005)' },
    { url: `${BASE}/policy/health`, label: 'Policy (8003)' },
    { url: `${BASE}/integrity/health`, label: 'Integrity (8008)' },
    { url: `${BASE}/explain/health`, label: 'Explainability (8009)' },
    { url: `${BASE}/geo/health`, label: 'GeoRisk (8006)' },
    { url: `${BASE}/graph/health`, label: 'Graph (8001)' },
    { url: `${BASE}/oracle/health`, label: 'Oracle Service (3001)' },
    { url: `${BASE}/zknaf/zknaf/health`, label: 'zkNAF (8010)' },
    { url: `${BASE}/fca/compliance/health`, label: 'FCA Compliance (8002)' },
  ];
  for (const t of services) {
    const r = await measure(t.url, { label: t.label });
    console.log(fmt(r));
    await sleep(100);
  }

  // ── Section 4: Real Workloads ──
  console.log('\n── REAL WORKLOADS (ML inference, fan-out, screening) ──');
  const workloads = [
    { url: `${BASE}/risk/score`, label: 'ML Risk Scoring (XGBoost)', method: 'POST', body: riskBody },
    { url: `${BASE}/sanctions/sanctions/check`, label: 'Sanctions Screening', method: 'POST', body: sanctionsBody },
    { url: `${BASE}/api/evaluate`, label: 'Full Pipeline (7-svc fan-out)', method: 'POST', body: riskBody },
    { url: `${BASE}/geo/geo/country-risk?country_code=IR`, label: 'GeoRisk — Iran (high risk)' },
    { url: `${BASE}/geo/geo/country/GB`, label: 'GeoRisk — UK (low risk)' },
    { url: `${BASE}/monitoring/alerts`, label: 'Active Monitoring Alerts' },
    { url: `${BASE}/integrity/health`, label: 'Integrity Verification' },
  ];
  for (const t of workloads) {
    const r = await measure(t.url, { ...t, label: t.label });
    console.log(fmt(r));
    await sleep(150);
  }

  // ── Section 5: Repeat key tests 3x for avg ──
  console.log('\n── LATENCY CONSISTENCY (3 runs each) ──');
  const repeats = [
    { url: `${BASE}/risk/score`, label: 'Risk Score', method: 'POST', body: riskBody },
    { url: `${BASE}/api/evaluate`, label: 'Full Pipeline', method: 'POST', body: riskBody },
    { url: `${BASE}/api/data/stats`, label: 'Stats API' },
  ];
  for (const t of repeats) {
    const runs = [];
    for (let i = 0; i < 3; i++) {
      const r = await measure(t.url, t);
      runs.push(r);
      await sleep(150);
    }
    const ttfbs = runs.map((r) => r.ttfb);
    const avg = ttfbs.reduce((a, b) => a + b, 0) / ttfbs.length;
    const min = Math.min(...ttfbs);
    const max = Math.max(...ttfbs);
    console.log(`  ${t.label.padEnd(20)} Avg: ${avg.toFixed(0).padStart(5)}ms  Min: ${min.toFixed(0).padStart(5)}ms  Max: ${max.toFixed(0).padStart(5)}ms  [${runs.map((r) => r.status).join(',')}]`);
  }

  // ── Section 6: Compare public vs direct (Cloudflare overhead) ──
  console.log('\n── CLOUDFLARE OVERHEAD (public vs direct localhost) ──');
  const comparisons = [
    { pub: `${BASE}/risk/health`, direct: `${LOCAL}:8000/health`, label: 'Risk Health' },
    { pub: `${BASE}/risk/score`, direct: `${LOCAL}:8000/score`, label: 'Risk Score', method: 'POST', body: riskBody },
    { pub: `${BASE}/api/data/stats`, direct: `${LOCAL}:3005/api/data/stats`, label: 'Stats API' },
  ];
  for (const t of comparisons) {
    const pub = await measure(t.pub, t);
    await sleep(100);
    const dir = await measure(t.direct, t);
    const overhead = pub.ttfb - dir.ttfb;
    console.log(`  ${t.label.padEnd(20)} Public: ${pub.ttfb.toFixed(0).padStart(5)}ms  Direct: ${dir.ttfb.toFixed(0).padStart(5)}ms  Overhead: +${overhead.toFixed(0)}ms`);
    await sleep(100);
  }

  console.log('\n══════════════════════════════════════════════════════════════════');
  console.log('  Test complete. All times include: TLS handshake + Cloudflare');
  console.log('  CDN + QUIC tunnel (London PoP) + nginx reverse proxy + service.');
  console.log('══════════════════════════════════════════════════════════════════');
}

run().catch(console.error);
