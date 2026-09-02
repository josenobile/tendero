# Devpost submission — paste-ready fields

Deadline: **Sep 3, 2026 · 15:00 Bogotá / 13:00 PT**. Submit at https://webmcp.devpost.com → "Enter a Submission".

---

## Project name
Tendero

## Elevator pitch (one line, ~200 char)
The default WebMCP commerce tools assume a prepaid card, a street address, a self-serve checkout — all wrong outside the US. Tendero registers the ten tools a Colombian sale actually needs, and the last refuses to charge without a human.

## "What it does" / story (paste the four required points)
> Source: docs/DEVPOST.md — sections (a) fit for WebMCP, (b) better UX, (c) what humans+agents can now do together, (d) how WebMCP was implemented, plus Potential impact and the Verified table. Paste it whole.

## Built with
JavaScript · WebMCP (`document.modelContext.registerTool`) · Python (reference domain, `tests/parity`) · Wompi (Colombian payments, sandbox) · Cloudflare/GitHub Pages · GitHub Actions

## Try it out (links)
- Live: https://josenobile.github.io/tendero/   (add `?lang=en` for English chrome)
- Repo: https://github.com/josenobile/tendero  (MIT)
- Demo prompt to paste into a WebMCP host: «Agregá jabón y leche, cotizá el envío a Leticia y decime cómo puede pagar el cliente»

## Video (YouTube, <3 min, public)
_(fill after upload)_  → https://youtu.be/__________

---

## Pre-submission checklist (rules)
- [ ] Live URL opens in ChatGPT in-app browser / Chrome-with-WebMCP  ✅ live, HTTP 200
- [ ] Public repo with OSS license visible in About  ✅ MIT
- [ ] `document.modelContext.registerTool(...)` present in repo  ✅ 10 tools
- [ ] Text description covers the 4 required points  ✅ docs/DEVPOST.md
- [ ] Demo video <3 min, PUBLIC YouTube, with audio  ⏳ file ready, needs upload
- [ ] Video plays logged-out  ⏳ verify after upload
- [ ] Wompi SANDBOX keys pasted into window.WOMPI (for the live payment step)  ⏳ needs Jose

## Two actions that still need Jose's login (cannot be done headlessly)
1. **Wompi sandbox keys** → comercios.wompi.co (free, instant) → paste `pub_test_…` + `test_integrity_…` into `static/index.html` `window.WOMPI`, redeploy. Only then does the live page's `iniciar_pago` open a real checkout.
2. **YouTube upload + Devpost submit** → needs your Google/Devpost session. Either you do it, or approve me driving your real browser via the shared-Chrome bridge (I'll confirm each irreversible step).
