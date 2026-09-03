# Devpost submission — Tendero

**Live URL:** https://josenobile.github.io/tendero/
**Repo:** https://github.com/josenobile/tendero (MIT, licence visible in the repo root)
**Video:** https://youtu.be/0z1ICokbFfw

---

## Elevator

**The default WebMCP commerce tool set is not neutral. It is a policy artifact that
exports US assumptions.** `search_products` / `add_to_cart` / `checkout` quietly encode a
prepaid card, a street address and a self-serve checkout. A Colombian sale is none of
those. Tendero is a working corner-store storefront — Surtitienda La Milagrosa, Manrique,
Medellín — that hands an agent the **eleven tools a Colombian sale actually requires**. Ten
of them advise, validate, quote and stage; the eleventh can close the sale, but only in
Wompi sandbox — no real money moves — and only after a human's one-click authorization the
agent structurally cannot bypass.

---

## Try it in 60 seconds

1. Open **https://josenobile.github.io/tendero/** in a browser with WebMCP and look at the
   surface panel: **4 tools** — `buscar_productos`, `validar_documento_dian`,
   `agregar_al_carrito`, `quitar_del_carrito`.
2. Give the agent the page's own demo prompt, verbatim:

   > **«Agregá jabón y leche, cotizá el envío a Leticia y decime cómo puede pagar el cliente»**

3. What you will see, with **no human click anywhere in it**:
   - the agent resolves the free text «jabón» and «leche» to SKUs, the cart fills, and the
     surface goes **4 → 7**;
   - it quotes freight to Leticia (DANE 91001): **$86.435**, Inter Rapidísimo, 7–11 días
     hábiles — and the surface goes **7 → 11**, `metodos_de_pago`, `confirmar_pedido`,
     `iniciar_pago` and `confirmar_pago` appearing because only now do they mean anything;
   - `metodos_de_pago` has **rewritten its own description** and reports contra entrega as
     unavailable: *Leticia «solo tiene acceso aéreo o fluvial»*. Order total **$110.835**
     (mercancía $24.400 + flete $86.435).
   - every panel the agent touched is badged **🤖 llamado por el agente**.
4. Two more prompts that a generic commerce tool set cannot answer at all:
   - *«El NIT del cliente es 900123456-0»* → **INVÁLIDO: dígito de verificación
     incorrecto… se recibió 0, corresponde 8.**
   - *«Preparame el pedido»* → the agent stages the order and **stops**. Click
     **Confirmar pedido** yourself and it seals: an order number of the form
     **SLM-YYYYMMDD-NNNN** (generated per order), panel reading
     **🤖 preparado por el agente · ✋ aprobado por vos**.

---

## (a) Why this use case is a strong fit for WebMCP

WebMCP lets a *page* hand an agent its own tools, in the user's own session, with the
page's own knowledge. That matters most where **the correct action depends on local rules
the agent cannot infer** and the page is the only party that knows them.

| The generic tool assumes | What a Colombian sale actually is |
|---|---|
| The buyer has a prepaid card | **Cash on delivery is the dominant rail** outside the big cities — with a collection ceiling, partial carrier coverage, and seven municipalities where no carrier will collect at all |
| A shipping address is just a field | **The tax owed depends on the destination department.** The same coffee legitimately costs less in Leticia |
| Tax is a percentage added at the end | Colombia has **four VAT treatments** plus consumption tax; *exento* and *excluido* are different in law, with different consequences for the seller |
| Checkout is final | The buyer holds a statutory **five-business-day** right of withdrawal, counted against a calendar with 18 public holidays, twelve of which shift to Monday |
| Identity is an email address | An electronic invoice is **rejected by the tax authority** without a valid document type and, for a company, a correct NIT check digit |

A generic agent that adds items and "checks out" produces a sale that is wrong on tax,
wrong on payment and wrong on paperwork — rejected-by-the-tax-authority wrong. The page is
the only actor that can know this, which is exactly the gap WebMCP exists to close. It is
also why this cannot be a server-side MCP integration: the knowledge belongs to the
merchant's page, and the cart is browser state.

## (b) How it creates a better user experience

- **The surface matches what is currently possible.** An agent arriving at a clean page
  sees 4 tools, not 11. There is nothing to hallucinate an order out of, so it doesn't.
- **Tools change meaning, not just availability.** Fix a destination and `metodos_de_pago`
  rewrites its own description to say this municipality has no road access and the basket
  contains VAT-excluded lines. Re-registration fires `toolchange`, so the agent re-reads
  the rules instead of carrying a stale mental model.
- **Refusals are useful.** Tools return *why*, in recovery-shaped text: the NIT check digit
  that should have been 8, the rail that cannot reach that town. The customer gets an
  explanation, not a missing button.
- **The human sees the machine work.** Every `execute` calls the same render function the
  human buttons call, then flashes and badges the panel **🤖 llamado por el agente**. A tool
  that only returns JSON is invisible to the person supervising it.
- **It degrades to a normal shop.** With no `document.modelContext` the page is still a
  complete storefront — human controls and agent tools call the same code path.

## (c) What people and agents can do together that was difficult or impossible before

**Before:** a shopper asks an assistant to buy something, and the assistant either fails at
checkout or completes a sale that is legally malformed — wrong VAT treatment, a payment
method that does not physically reach the buyer's town, an invoice DIAN will bounce.

**Now:** the agent assembles the order and the *page supplies the law* — which of the four
VAT treatments each line takes, whether cash on delivery can reach that municipality and
under what ceiling, when the withdrawal window closes against the real holiday calendar,
and whether the buyer's document will survive electronic invoicing. Then the split that
makes this collaboration rather than automation:

> **`confirmar_pedido` stages the order and does not commit it.** The agent validates,
> liquidates and assembles; the page renders exactly what will happen and waits. A **human
> click** on *Confirmar pedido* seals it (an order number of the form **SLM-YYYYMMDD-NNNN**,
> generated per order), and the artifact
> is stamped with both hands — **🤖 preparado por el agente · ✋ aprobado por vos**.

The agent knows the catalogue, the tax treatment, the carrier coverage and the withdrawal
deadline. The person takes responsibility for the sale. Neither could do this alone: the
agent cannot know Colombian retail law, and the shopkeeper cannot compute five tax
liquidations, a volumetric freight quote and a business-day window per order.

## (d) How WebMCP was implemented

- **Eleven tools**, each `document.modelContext.registerTool({ name, description,
  inputSchema, execute })` with full JSON Schema — enums, `additionalProperties: false`,
  `format: date`, bounds, and a category enum populated from the live catalog.
- **Progressive disclosure in three rungs** gated on page state (cart empty → cart has
  items → destination fixed): **4 → 7 → 11**. The agent walks the rungs itself; the three
  tools with `readOnlyHint: false` are precisely the ones that move it.
- **Descriptions computed from state**, so a change forces genuine re-registration and a
  real `toolchange` event. The page renders its surface panel *from that event*, so the
  panel reflects the browser's truth rather than the page's own bookkeeping.
- **Responses in proper MCP shape**: `content[0].text` carries a human-readable summary
  first, then JSON, plus `structuredContent`. Errors return `isError` with text naming what
  is missing.
- **Annotations used discriminately** — `readOnlyHint`, `idempotentHint`, `destructiveHint`,
  and `untrustedContentHint` on merchant- and carrier-sourced copy.
- **Host-portable teardown**: deregistration probes `unregisterTool`, then the handle's own
  `unregister`, then whole-surface `provideContext` replacement.
- **Envelope-tolerant `execute()`**: bare arguments, `{input}` and `{arguments}` all behave
  identically. Zero console errors on load.
- **No backend at runtime.** The site is static files; the Colombian rule engine runs *in
  the page* (`static/dominio.js`). The Python package in `src/tendero/` is the **reference
  implementation**, and `tests/parity/` pins the JavaScript to it — a divergence in any
  value, or even in an error string, fails CI.
- **CI (GitHub Actions):** `ruff`, `mypy --strict`, `pytest` with an 85 % coverage gate, and
  a job that loads the real page with a mock `modelContext` and asserts that an agent can
  grow the tool surface by itself.

## Potential impact

Two people sit on either side of this gap. A **corner-store owner** in Medellín already
sells over WhatsApp and has to get every invoice past the DIAN — a wrong document type or
NIT check digit bounces the whole electronic document, and the tax owed shifts with the
buyer's department. A **shopper** whose assistant "checks out" can have it silently choose
a payment rail that cannot physically reach their town. The commerce tools that ship in
every WebMCP demo make both cases *worse, confidently*, because they encode a checkout the
buyer does not have.

Colombia is the instance, not the point. The *shape* — the last mile of commerce is local
law the agent cannot infer, and the page is the only party that knows it — repeats in
Brazil (NF-e, CPF/CNPJ), Mexico (CFDI, RFC), India (GSTIN, UPI-first). Swap the rule
module and the same page registers the tools that jurisdiction needs. Adoption is one
static file and a `<script>`: no backend, nothing to keep alive, MIT-licensed.

## Verified

Probed against the **deployed** page with a mock `document.modelContext`, driving it exactly
as an agent would:

| Step | Tools registered |
|---|---|
| Clean page load | **4** — `buscar_productos`, `validar_documento_dian`, `agregar_al_carrito`, `quitar_del_carrito` |
| Agent calls `agregar_al_carrito` (free text "jabón", "leche" → SKUs) | **7** — `calcular_total_con_iva`, `consultar_derecho_retracto`, `cotizar_envio` appear |
| Agent calls `cotizar_envio` for Leticia (91001) | **11** — `metodos_de_pago` (description rewritten for a road-less municipality), `confirmar_pedido`, `iniciar_pago` and `confirmar_pago` appear |
| Agent calls `confirmar_pedido` | still **11** — the order is **staged, not committed** |
| **Human clicks "Confirmar pedido"** | order sealed with a number of the form **SLM-YYYYMMDD-NNNN** (generated per order), panel: **🤖 preparado por el agente · ✋ aprobado por vos** |
| Agent calls `iniciar_pago` (after the human seal) | a **Wompi sandbox** checkout URL is issued, carrying the exact VAT/consumption tax the page computed (tax-in-cents); it refuses unless the order was human-sealed and sandbox keys are configured |
| Agent calls `confirmar_pago` | the sale **closes in sandbox** — Wompi's **APROBADA** result (a `SBX-…` id, entorno sandbox), painting a **✅ PAGO APROBADO · SANDBOX** panel; no real money moves |
| `confirmar_pago` before the human seal / before `iniciar_pago` | **refused** — it will not close a sale until an order is staged, a human has sealed it, and `iniciar_pago` has issued the checkout |

**No human click occurred in rungs 1–3.** The one human click in the whole flow is the
authorizing seal on *Confirmar pedido* — and only after it can `iniciar_pago` open the Wompi
sandbox checkout and `confirmar_pago` close the sale. By design.

Also verified live on the deployed page:
- NIT `900123456-0` → *«INVÁLIDO: dígito de verificación incorrecto… se recibió 0,
  corresponde 8»*.
- Contra entrega to Leticia → refused: *«solo tiene acceso aéreo o fluvial»*.
- The page's own demo prompt runs end to end: flete **$86.435** (Inter Rapidísimo, 7–11
  días hábiles), total **$110.835**.

## Honest notes

- Carrier tariffs, the merchant's identity and product prices are **invented demonstration
  data**. The tax rules, collection ceilings, holiday calendar and NIT check-digit algorithm
  are real and cited to the statute inline in each tool description.
- Payment runs in **Wompi sandbox only — no real money moves**. Ten of the eleven tools
  advise, validate, quote and stage; the eleventh, `confirmar_pago`, can close the sale, but
  only after a human's one-click authorization the agent structurally cannot bypass:
  `confirmar_pago` refuses until an order is staged, a human has sealed it, and `iniciar_pago`
  has issued the checkout. The human authorizes the sale; the agent executes the payment.
