// Asserts, in CI, the property that actually matters for a WebMCP app:
// an agent arriving at the page can reach the whole tool surface by itself.
//
// This exists because a registered tool is not necessarily a working one. A previous
// revision declared the cart writers correctly — right name, right schema, right
// annotations — and threw `acciones[h.nombre] is not a function` the moment an agent
// called them. Code review passed it. Only executing it caught it.
//
// The page is served from disk and driven with a mock document.modelContext, so this
// needs no network and no WebMCP-capable browser.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import puppeteer from 'puppeteer';

const ROOT = new URL('../../static/', import.meta.url).pathname;
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' };

const server = createServer(async (req, res) => {
  const rel = req.url === '/' ? 'index.html' : decodeURIComponent(req.url.slice(1)).split('?')[0];
  try {
    const body = await readFile(join(ROOT, rel));
    res.writeHead(200, { 'Content-Type': TYPES[extname(rel)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end('not found');
  }
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}/`;

const MOCK = () => {
  const reg = new Map();
  const api = {
    registerTool(d) {
      reg.set(d.name, d);
      (window.__defs ??= {})[d.name] = d;
      return { unregister: () => reg.delete(d.name) };
    },
    unregisterTool(n) { reg.delete(n); delete (window.__defs ??= {})[n]; },
    provideContext(ctx) {
      reg.clear(); window.__defs = {};
      for (const t of ctx?.tools ?? []) { reg.set(t.name, t); window.__defs[t.name] = t; }
    },
  };
  Object.defineProperty(document, 'modelContext', { value: api, configurable: true });
  window.__names = () => Array.from(reg.keys());
};

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
const page = await browser.newPage();
const consoleErrors = [];
page.on('pageerror', (e) => consoleErrors.push(String(e).slice(0, 200)));
await page.evaluateOnNewDocument(MOCK);
await page.goto(base, { waitUntil: 'networkidle2' });
await new Promise((r) => setTimeout(r, 2000));

const result = await page.evaluate(async () => {
  const names = () => window.__names();
  const call = async (n, a) => {
    const d = window.__defs?.[n];
    if (!d) return { tool: n, missing: true };
    try {
      const r = await d.execute(a);
      await new Promise((x) => setTimeout(x, 600));
      return { tool: n, isError: !!r?.isError, structured: !!r?.structuredContent };
    } catch (e) { return { tool: n, threw: String(e).slice(0, 120) }; }
  };
  const clean = names();
  const add = await call('agregar_al_carrito',
    { lineas: [{ consulta: 'jabon', cantidad: 2 }, { consulta: 'leche', cantidad: 2 }] });
  const withCart = names();
  const ship = await call('cotizar_envio', { destino: '91001' });
  const withDest = names();
  return { clean, add, withCart, ship, withDest };
});

await browser.close();
server.close();

const fail = [];
const need = (cond, msg) => { if (!cond) fail.push(msg); };

need(result.clean.includes('agregar_al_carrito'),
  'agregar_al_carrito is not registered on a clean page — an agent cannot start');
need(!result.add.missing && !result.add.threw && !result.add.isError,
  `agregar_al_carrito did not execute cleanly: ${JSON.stringify(result.add)}`);
need(result.add.structured, 'agregar_al_carrito returned no structuredContent');
need(result.withCart.length > result.clean.length,
  `the tool surface did not grow after the agent filled the cart (${result.clean.length} -> ${result.withCart.length})`);
need(result.withDest.includes('metodos_de_pago'),
  'metodos_de_pago did not appear after the agent set a destination');
need(consoleErrors.length === 0, `page errors: ${consoleErrors.join(' | ')}`);

console.log(`clean:      ${result.clean.length}  ${result.clean.join(', ')}`);
console.log(`with cart:  ${result.withCart.length}`);
console.log(`with dest:  ${result.withDest.length}  ${result.withDest.join(', ')}`);

if (fail.length) {
  console.error('\nFAILED:\n- ' + fail.join('\n- '));
  process.exit(1);
}
console.log('\nOK — an agent can reach the full tool surface with no human interaction.');
