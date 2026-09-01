# Devpost submission — Tendero

**Live URL:** https://josenobile.github.io/tendero/
**Repo:** https://github.com/josenobile/tendero (MIT)
**Video:** _(pending — <3 min, public YouTube, with audio)_

---

## Elevator

**The default WebMCP commerce tool set is not neutral. It is a policy artifact that
exports US assumptions.** `search_products` / `add_to_cart` / `checkout` quietly encode
a prepaid card, a street address, and a self-serve checkout. A Colombian sale is none of
those. Tendero registers the tools a Latin American sale actually requires.

---

## Why this use case is a strong fit for WebMCP

WebMCP lets a *page* hand an agent its own tools, in the user's own session, with the
page's own knowledge. That matters most where **the correct action depends on local rules
the agent cannot infer** and the page is the only party that knows them.

Colombian retail is the sharpest example we could find:

| The generic tool assumes | What a Colombian sale actually is |
|---|---|
| The buyer has a prepaid card | **Cash on delivery is the dominant rail** outside the big cities — with a collection ceiling, partial carrier coverage, and municipalities where no carrier will collect at all |
| A shipping address is just a field | **The tax owed depends on the destination department.** The same coffee legitimately costs less in Leticia |
| Tax is a percentage added at the end | Colombia has **four VAT treatments**; *exento* and *excluido* are different in law with different consequences for the seller |
| Checkout is final | The buyer holds a statutory **five-business-day** right of withdrawal, counted against a calendar with 18 public holidays, twelve of which shift to Monday |
| Identity is an email address | An electronic invoice is **rejected by the tax authority** without a valid document type and, for a company, a correct NIT check digit |

A generic agent that adds items and "checks out" produces a sale that is wrong on tax,
wrong on payment, and wrong on paperwork. Not slightly wrong — rejected-by-the-tax-
authority wrong. The page is the only actor that can know this, which is precisely the
gap WebMCP exists to close.

## How it creates a better user experience

The tool surface **changes as the conversation progresses**. An agent arriving at a clean
page sees only what makes sense with no cart. Add products and the order tools appear.
Set a destination and `metodos_de_pago` *rewrites its own description* to warn that this
municipality has no road access and that the basket contains VAT-excluded lines — which
forces re-registration and a `toolchange`, so the agent re-reads the rules rather than
carrying a stale mental model.

Every tool call paints the page and badges the panel **"🤖 llamado por el agente"**, so a
human watching sees exactly what the agent did and why. The page is a working storefront
with no agent present at all.

## What people and agents can do together that was difficult or impossible before

Before: a shopper asks an assistant to buy something, and the assistant either fails at
checkout or completes a sale that is legally malformed — wrong VAT treatment, a payment
method that does not reach the buyer's town, an invoice the DIAN will bounce.

Now: the agent assembles the order, and the *page* supplies the law — which of the four
VAT treatments each line takes, whether cash-on-delivery can physically reach that
municipality and under what ceiling, when the withdrawal window closes against the real
holiday calendar, and whether the buyer's document will survive electronic invoicing.
The human stays in the loop for the part that should never be automated: committing the
sale.

## How WebMCP was implemented

- `document.modelContext.registerTool({ name, description, inputSchema, execute })` for
  every tool, with full JSON Schema — enums, `additionalProperties: false`, `format: date`,
  bounds, and a category enum populated from the live catalog.
- **Progressive disclosure**: tools are registered in rungs gated on page state, so the
  surface an agent sees matches what is currently possible.
- **Descriptions that mutate with state**, triggering genuine re-registration and
  `toolchange` — the agent is told when the rules change under it.
- Responses in proper MCP shape: `content[0].text` carries a human-readable summary
  first, then JSON, plus `structuredContent`.
- Annotations used discriminately — `readOnlyHint`, `idempotentHint`, and
  `untrustedContentHint` on merchant- and carrier-sourced copy.
- Errors return `isError` with recovery-shaped text that names what is missing.
- Deregistration probes `unregisterTool` → the handle's `unregister` → whole-surface
  `provideContext` replacement, so the surface stays correct across host implementations.
- The Colombian rule engine runs **in the page** (`static/dominio.js`), with
  `tests/parity/` pinning the JavaScript to the Python reference implementation — a
  divergence in any value, or even an error string, fails CI.

## Verified

The tool surface was probed against the deployed page with a mock `document.modelContext`,
driving it exactly as an agent would:

| Step | Tools registered |
|---|---|
| Clean page load | **4** — `buscar_productos`, `validar_documento_dian`, and the two cart writers |
| Agent calls `agregar_al_carrito` (free text "jabón", "leche" → SKUs) | **7** — `calcular_total_con_iva`, `consultar_derecho_retracto`, `cotizar_envio` appear |
| Agent calls `cotizar_envio` for Leticia (91001) | **8** — `metodos_de_pago` appears, its description rewritten for a municipality with no road access |

No human click at any point. `execute()` accepts the bare, `{input}` and `{arguments}`
envelopes identically. The page's own demo prompt — «Agregá jabón y leche, cotizá el envío
a Leticia y decime cómo puede pagar el cliente» — runs to completion, ending at
$175.825 (mercancía $48.800 + flete $127.025).
