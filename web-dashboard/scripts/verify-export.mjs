// Structural checks on the static export in out/.
// Usage: node scripts/verify-export.mjs [expectedBasePath]
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';

const out = path.resolve(import.meta.dirname, '..', 'out');
const base = (process.argv[2] ?? '').replace(/\/+$/, '');
const failures = [];
const check = (ok, msg) => {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${msg}`);
  if (!ok) failures.push(msg);
};

function walk(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = path.join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

for (const route of ['index.html', 'ground/index.html', 'console/index.html']) {
  check(existsSync(path.join(out, route)), `out/${route} exists`);
}
const files = existsSync(out) ? walk(out) : [];
const text = files.filter((f) => /\.(html|js|css|txt|json)$/.test(f));
const remote = text.filter((f) => /fonts\.(googleapis|gstatic)\.com|cdn\.jsdelivr|unpkg\.com/.test(readFileSync(f, 'utf8')));
check(remote.length === 0, `no runtime font/CDN URLs (${remote.map((f) => path.relative(out, f)).join(', ') || 'none'})`);
check(files.some((f) => f.endsWith('.woff2')), 'self-hosted .woff2 fonts emitted');

const html = ['ground/index.html', 'console/index.html', 'index.html'].map((r) => [r, readFileSync(path.join(out, r), 'utf8')]);
for (const [r, h] of html) {
  check(h.includes(`${base}/_next/static/`), `${r} references assets under "${base}/_next/static/"`);
  const visible = h.replace(/<script[\s\S]*?<\/script>/g, ' ').replace(/<style[\s\S]*?<\/style>/g, ' ').replace(/<[^>]+>/g, ' ');
  const banned = ['V97', 'V06', 'V16', 'V35', '600 baud', '1200 baud', '100%', '0 dB', 'Luminary 99', 'Colossus 249', 'kebal', 'bebas exploit'];
  const hits = banned.filter((b) => visible.includes(b));
  check(hits.length === 0, `${r} has no banned claims (${hits.join(', ') || 'none'})`);
}

const keyLeak = text.filter((f) => /APOLLO26_(LINK|OPERATOR)_KEY\s*=/.test(readFileSync(f, 'utf8')));
check(keyLeak.length === 0, 'no environment key assignments in the bundle');

console.log(failures.length === 0 ? 'ALL CHECKS PASSED' : `${failures.length} CHECK(S) FAILED`);
process.exit(failures.length === 0 ? 0 : 1);
