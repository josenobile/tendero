# Tendero

> **The default commerce tool set is not neutral. It exports US assumptions.**
> `search_products` / `add_to_cart` / `checkout` quietly encode a prepaid card, a
> street address and a self-serve checkout. A Colombian sale is none of those.
> **Tendero registers the eleven tools a Latin American sale actually requires** —
> ten advise, validate, quote and stage; the eleventh can close the sale, but only in
> Wompi sandbox (no real money moves) and only after a human's one-click authorization the
> agent structurally cannot bypass.

- **Live storefront:** **<https://josenobile.github.io/tendero/>** — static, no backend, no build step
- **Repo:** <https://github.com/josenobile/tendero> · MIT
- **Video:** _(under 3 minutes, public, with audio)_

**The tool surface grows under the agent's own hands — measured in a browser, with no
human click at any point:**

| Moment | Tools registered |
| --- | --- |
| Clean page load | **4** — `buscar_productos`, `validar_documento_dian`, `agregar_al_carrito`, `quitar_del_carrito` |
| The agent calls `agregar_al_carrito` (free text «jabón», «leche» → SKUs) | **7** — `calcular_total_con_iva`, `consultar_derecho_retracto`, `cotizar_envio` appear |
| The agent calls `cotizar_envio` for Leticia (91001) | **11** — `metodos_de_pago`, `confirmar_pedido`, `iniciar_pago` and `confirmar_pago` appear, the first with its description rewritten for a municipality with no road access |

Then `confirmar_pedido` **stages** the order and stops. A human clicks **«Confirmar
pedido»** to seal it (an order number of the form `SLM-YYYYMMDD-NNNN`, generated per order),
and the panel reads **🤖 preparado por el
agente · ✋ aprobado por vos**. The agent knows the catalogue, the VAT treatment, the
carrier coverage and the withdrawal window; the person takes responsibility for the sale.

Spanish-language storefront (it is a Medellín corner store; that is the point), English
documentation.

---

## The thesis

WebMCP lets a page hand an AI agent its own tools:

```js
document.modelContext.registerTool({ name, description, inputSchema, execute });
```

The obvious tool set — search the catalog, view a product, add to cart, check out — is
already shipping. It is not neutral. It encodes assumptions that are true in the United
States and false almost everywhere else:

| The assumption | What a Colombian sale actually is |
| --- | --- |
| The buyer has a prepaid card | **Cash on delivery is the dominant rail** outside the big cities — and it has a collection ceiling, partial carrier coverage, and seven municipalities where it does not exist at all |
| A shipping address is just a field | **The tax owed depends on the destination department.** The same coffee costs less in Leticia, and not because of freight |
| Tax is a percentage added at the end | Colombia has **four** VAT treatments, and *exento* and *excluido* are different things in law with different consequences for the seller |
| Checkout is final | The buyer has a statutory **five business day** right of withdrawal, counted against a calendar with 18 public holidays, twelve of which move to Monday |
| Identity is an email address | An electronic invoice is **rejected by the tax authority** without a valid document type and, for a company, a correct NIT check digit |

A field of US developers will not think of these. That is the creativity. They are real
law and real logistics that block real money. That is the impact.

The storefront is **Surtitienda La Milagrosa**, a corner store in Manrique, Medellín. It
is modelled as a corner store on purpose: a Colombian grocery basket crosses all five tax
treatments at once — plantain is *excluido*, milk is *exento*, coffee is 5 %, soap is
19 %, and the set lunch pays consumption tax instead of VAT. A seven-line cart already
forces five different liquidations.

## Who this is for

Two people, one gap between them:

- **The shopkeeper** in Manrique who already sells over WhatsApp and has to get an
  electronic invoice past the DIAN — a wrong document type or NIT check digit bounces the
  whole document, and the tax owed changes with the buyer's department. Today no assistant
  helps with that; the generic tool set does not even know these rules exist.
- **The shopper** whose AI assistant "checks out" and silently picks a payment rail that
  cannot physically reach their town, or an address-only flow that ignores the fact that
  cash on delivery is how the sale actually happens.

The tools that ship in every WebMCP commerce demo make both of these worse, confidently,
because they encode a checkout the buyer does not have.

## Colombia is the instance; the shape is the point

Nothing here is Colombia-specific except `dominio.js`. The *pattern* — that the last mile
of commerce is local law the agent cannot infer, and the page is the only party that
knows it — repeats everywhere the US defaults break: **Brazil** (NF-e, CPF/CNPJ),
**Mexico** (CFDI, RFC), **India** (GSTIN, UPI-first payment). Swap the rule module and the
same page registers the tools that jurisdiction actually needs. The adoption path is one
static file and a `<script>` — no service to run, no backend to keep alive, MIT-licensed.

---

## The eleven tools

Six exist because a specific Colombian rule makes the generic version wrong. Two exist
because an agent must be able to *build* the order, not just read it. One exists
because an agent must be able to *finish* the work without *committing* it. The last two
carry the sealed order into payment — a Wompi **sandbox** checkout and its approved result —
and run only after a human's authorizing click. Every one is
registered with a full JSON Schema and a description written for an agent to read — the
descriptions cite the statute, because an agent that cannot cite the rule will invent one.

### 1. `buscar_productos` — the price is a function of the destination

Returns each reference with its tax regime *and its shelf price computed for the
destination*. Article 423 of the Estatuto Tributario excludes San Andrés and Providencia
from VAT; article 270 of Ley 223 de 1995 does the same for Amazonas, Guainía and Vaupés.
The same 250 g of Antioquian coffee is `$14.900` in Medellín and `$14.200` in Leticia. A
tool that returns one price is returning a wrong one.

`readOnlyHint` · `untrustedContentHint` (merchant-authored product copy)

### 2. `cotizar_envio` — seven towns where cash on delivery cannot exist

Quotes freight with five carriers and answers the question that actually blocks the sale:
**does this destination accept cash on delivery?** Leticia, Puerto Nariño, Mitú, Inírida,
Puerto Carreño, San Andrés and Providencia have no road. Freight goes as air cargo, a
local agent makes the final delivery, and *no carrier will collect cash there*. Volumetric
weight at the Colombian 6000 factor with a one-kilo billing floor; declared-value handling
fees; per-carrier collection ceilings.

`readOnlyHint: false` — it **writes**: it fixes the page's shipping destination, which is
what opens the last rung. See [the dynamic surface](#the-dynamic-surface).

### 3. `validar_documento_dian` — the check digit that rejects the invoice

Six identity types with their codes from DIAN's electronic-invoicing technical annex
(CC 13, CE 22, NIT 31, PA 41, TI 12, PEP 47), each with its own length and character
rules. For a NIT it verifies the check digit with the real algorithm — digits weighted
right to left by the official prime series, summed modulo 11, remainder 0 or 1 giving 0
and anything else giving `11 − r` — and **computes it when the customer did not dictate
it**, because a corner-store customer never knows it. One wrong digit rejects the entire
electronic document: `900123456-0` comes back *«INVÁLIDO: dígito de verificación
incorrecto… se recibió 0, corresponde 8»*.

Asserted against genuine Colombian NITs: Bancolombia `890903938-8`, DIAN itself
`800197268-4`, Grupo Éxito `890900608-9`, Servientrega `860512330-3`.

`readOnlyHint`

### 4. `calcular_total_con_iva` — *exento* is not *excluido*

- **19 %** general rate (art. 468 ET)
- **5 %** reduced rate — coffee, flour, pasta, cured meats (art. 468-1 ET)
- **Exento** — zero-rated (art. 477 ET: meat, milk, eggs). The seller **keeps** the right
  to deduct input VAT. The invoice carries a tax line at 0.00 %.
- **Excluido** — outside the tax (art. 424 ET: fresh produce, panela, rice). The seller
  **loses** that right; input VAT becomes cost. No tax line at all.
- **INC 8 %** — prepared food pays consumption tax *instead of* VAT (art. 512-1)

Plus the territorial override that switches VAT off entirely by destination. All
arithmetic is on integer centavos with explicit `ROUND_HALF_UP`, computed **per line and
then summed** — DIAN validates that per-line tax adds up to the document total, and half a
centavo of drift rejects the invoice.

The response also reports how much of the sale keeps the right to deductible input VAT,
which is the practical consequence of the exento/excluido difference: on the excluded
portion the VAT the shop paid its supplier is not recovered — it becomes cost, and if it
is not passed into the price the sale quietly loses margin.

`readOnlyHint`

### 5. `consultar_derecho_retracto` — five business days, against the real calendar

Article 47 of Ley 1480 de 2011 grants five **business** days from delivery — but only for
distance and non-traditional sales. Buy at the counter and there is no withdrawal right at
all.

The calendar is implemented, not tabulated: Easter from the anonymous Gregorian algorithm,
Maundy Thursday and Good Friday at −3 and −2, and the Emiliani law (Ley 51 de 1983) moving
twelve holidays to the following Monday, with Ascensión, Corpus Christi and Sagrado
Corazón at Easter +43, +64 and +71 — deltas that already include that shift. Delivered on
Maundy Thursday 2026-04-02, the window closes on 2026-04-10: **five business days is eight
calendar days.**

The article's own paragraph carves out perishables, custom-made goods and already-started
services — so an arepa is not returnable, and the tool detects that from the cart and says
*why*.

`readOnlyHint`

### 6. `metodos_de_pago` — rails, not buttons

Evaluates five Colombian rails against this order and **returns the ones that do not
apply, with the reason**, because the useful answer for a customer is not that cash on
delivery is missing but why. Asked for contraentrega to Leticia, it refuses: the town
*«solo tiene acceso aéreo o fluvial»*.

- **Nequi** is a low-value deposit and cannot move more than eight minimum wages per
  operation (Decreto 2555 de 2010)
- **PSE** cannot start without the buyer's bank
- **Cash on delivery** needs physical goods, carrier coverage and a ceiling
- **Card** is the only rail with instalments and the most expensive one

The merchant-side model includes the 1.5 % withholding the card acquirer applies and the
4x1000 financial-movements tax (art. 870 ET) that every rail eventually pays.
Annually-decreed values (UVT, minimum wage) live in a `ParametrosFiscales` object rather
than inline constants, so the system cannot quietly start a new year computing last year's
ceilings.

`readOnlyHint` · `untrustedContentHint` (carrier-sourced reasons)

### 7. `agregar_al_carrito` — the door to the surface

The cart is page state, so the tool that writes it is a thin wrapper over the page's own
`agregar(sku, delta)`. Each line is free text (`consulta`, resolved with the same
accent-tolerant search as `buscar_productos`) or an exact `sku`, plus a quantity. A
free-text line that matches more than one reference is **never guessed**: the tool returns
the candidates and asks the agent to disambiguate; a line that matches nothing comes back
`isError` with the search term named. It returns the recomputed cart, and it is the first
move of the growth mechanic — the first reference moves the page from rung 0 to rung 1,
no human click in between.

`readOnlyHint: false` · `idempotentHint: false` — it writes, and twice is not the same as once.

### 8. `quitar_del_carrito` — the way back out

Removes units of a reference by `sku`; omit `cantidad` to drop the whole line. It is the
exact inverse of `agregar_al_carrito` over the same page function, so there is no second
cart logic to drift, and an empty cart sends the surface back to rung 0.

`readOnlyHint: false` · `idempotentHint: false`

### 9. `confirmar_pedido` — the agent finishes the work and stops

The advisory tools calculate. This one **produces** something — and deliberately does not
close it. It assembles the complete order and leaves it *staged*, waiting for a human
click. Before staging anything it re-validates through the same rules the other tools
expose:

- **the buyer's document** through the DIAN rule, check digit included — a bad NIT comes
  back as a refusal naming the rule, and nothing is staged;
- **the payment rail** against what `metodos_de_pago` reports as actually available for
  *that* municipality — asking for contraentrega to a road-less town is refused with the
  carrier's reason;
- **a non-empty cart and a fixed destination** — an order without a municipality can
  neither be charged nor dispatched.

What it stages carries the per-treatment VAT breakdown, the freight, the ceiling of the
chosen rail, and the exact date the withdrawal window expires. Its own description says so
to the agent: *NO cobra, NO despacha y NO cierra la venta*. If a staged order already
exists, the description says that too, and that calling again replaces it.

`readOnlyHint: false` · `destructiveHint` · `idempotentHint: false`

---

## Humans and agents, together

This is the part that is not a storefront feature.

The agent does everything an agent is good at: resolve free text to SKUs, pick the tax
treatment per line, check the carrier's coverage, compute the withdrawal date against a
calendar with a moving Easter. Then it hits a wall it cannot cross by design. The order is
rendered on the page — line by line, with its freight, its payment ceiling and its
retracto deadline — and **a person clicks «Confirmar pedido»**.

Only that click mints the order number (of the form `SLM-YYYYMMDD-NNNN`, generated per order) and the panel changes to
**🤖 preparado por el agente · ✋ aprobado por vos**. Nothing in the tool surface can
produce that seal.

That asymmetry is the answer to *"what can humans and agents do together"*: not an agent
that shops for you, and not a form you fill in alone — an agent that carries the part of a
sale that is arithmetic and statute, handing a person the part that is consent.

---

## The dynamic surface

`registerTool` is easy. The interesting part of WebMCP is that the tool set is **not
static** — a page can change what an agent is allowed to do as its own state changes, and
announce it. Tendero uses
`document.modelContext.addEventListener("toolchange", …)` for real, not as decoration.

| Rung | Page state | Tools exposed | Why the others are absent |
| --- | --- | --- | --- |
| **0** | Empty cart | 4 — `buscar_productos`, `validar_documento_dian`, `agregar_al_carrito`, `quitar_del_carrito` | The others describe *an order*. With an empty cart they have nothing to operate on, and offering them invites an agent to hallucinate one. The cart writers stay: they are how the order gets built in the first place. |
| **1** | Cart has items | 7 — plus `calcular_total_con_iva`, `consultar_derecho_retracto`, `cotizar_envio` | Now there is an order: it can be liquidated, its withdrawal window computed and its freight quoted. |
| **2** | Destination fixed | 11 — plus `metodos_de_pago`, `confirmar_pedido`, `iniciar_pago`, `confirmar_pago` | The rails are a function of the municipality, and an order that cannot be dispatched cannot be staged. Only now do payment, staging and the sandbox checkout make sense. |

Two things make this more than a counter going up:

**The agent moves the surface itself.** The tools marked `readOnlyHint: false` are the two
cart writers, `cotizar_envio` and `confirmar_pedido`: adding a reference creates the order,
and quoting freight *fixes the page's destination*, which is exactly what a shopper does
when they type their city. So an agent that calls `agregar_al_carrito` walks the page from
rung 0 to rung 1 in a single move, and quoting freight afterwards opens rung 2 — eleven
tools, and no human click anywhere in that path.

**The description mutates with the state.** When the selected destination is one of the
seven road-less municipalities, `metodos_de_pago` is re-registered with a description that
carries the warning: *no hay vía terrestre, el contra entrega no existe allí*. When the
destination is VAT-excluded, it says so. When an order is already staged,
`confirmar_pedido` announces that calling it again replaces it. The tool changes meaning,
not just availability, and every re-registration fires `toolchange`.

The page listens to that event and renders the surface panel from it — the panel reflects
the browser's truth, not the page's own bookkeeping.

Deregistration probes `unregisterTool` → the handle's own `unregister` → whole-surface
`provideContext` replacement, so the rungs stay correct across host implementations.
`execute()` accepts the bare, `{input}` and `{arguments}` envelopes identically.

### Everything is painted into the DOM

Every `execute` calls the same render function the human buttons call, then flashes the
panel, badges it **🤖 llamado por el agente** and scrolls it into view. A tool that only
returns JSON is invisible in a video and unfalsifiable to a reviewer. Here, when an agent
calls a tool, a person watching the screen sees the page change.

### Graceful degradation

With no `document.modelContext`, the page shows a banner explaining what is missing and
**stays a working storefront**: search, cart, destination, freight, VAT, withdrawal window,
payment rails and the order confirmation all work from the page's own controls, because the
human controls and the agent tools call the same code path.

---

## Architecture — the rules run in the page

There is **no backend at runtime**. The site is static files, and the Colombian rule engine
is shipped to the browser:

```
static/index.html      one self-contained file: inline CSS + JS, no CDN, no build step
       │               registers the eleven tools, gates them by rung, paints every result
       ▼  import("./dominio.js")          ← the whole domain, in the page's own session
static/dominio.js      the Colombian rules as JavaScript: money, DIAN documents, freight,
                       VAT, retracto calendar, payment rails, catalogue
       ▲
tests/parity/          pins the JavaScript to the Python below — any divergence in a
       │               value, or even in an error string, fails CI
src/tendero/           the executable specification: pure rules, no network, no disk,
                       no clock. Unit-tested independently of any browser.
```

This is the point, not a compromise. WebMCP's premise is that **the page** hands the agent
its capabilities; a page whose rules live behind an HTTP call is renting them. Here the
tool surface, the arithmetic and the law all live in the same document the agent is talking
to — it works offline, it works from any static host, and there is no service to keep alive
for a judge to open the link six months from now.

The cost of shipping the rules twice is drift, so the drift is what CI tests: `tests/parity/`
drives both implementations over the same inputs and compares outputs *and* error messages.

| Module (`src/tendero/domain/`) | What it encodes |
| --- | --- |
| `dinero.py` | Integer COP centavos. Explicit `ROUND_HALF_UP`, cash rounding to the 50-peso coin, and a proportional split that cannot lose or invent a centavo. |
| `documento.py` | Six DIAN identity types, their annex codes, and the real NIT check-digit algorithm. |
| `envio.py` | 50 DANE-keyed municipalities in three tiers, five carriers with divergent coverage, volumetric weight, and the seven road-less destinations. |
| `impuesto.py` | The four VAT treatments plus INC, the territorial override, and UBL-shaped tax subtotals. |
| `retracto.py` | Easter, the 18 holidays, the Emiliani shift, business-day arithmetic and the article-47 carve-outs. |
| `pago.py` | Five rails with their regulatory ceilings, and the merchant's real net after commission, withholding and 4x1000. |
| `catalogo.py` | 24 references spanning all five treatments, priced per destination. |

The Python layer knows nothing about HTTP and nothing about WebMCP, so every rule is
unit-tested without starting a browser or a server.

---

## Run it

Any static file server works — the page loads `dominio.js` as an ES module, so open it over
`http://`, not `file://`:

```bash
python3 -m http.server 8000 --directory static
# open http://127.0.0.1:8000/
```

Deep-link straight into the interesting state:

```
http://127.0.0.1:8000/?carrito=ASE-JAB-X3:2,LAC-LEC-1L:3,CAF-TOS-250:1&destino=91001
```

That is a cart with three tax regimes shipping to Leticia: VAT switched off, no cash on
delivery, air-cargo surcharge, and `metodos_de_pago` carrying the road-less warning in its
own description.

### Try it with an agent

Open the page in a browser that exposes WebMCP and ask for something a generic commerce
tool set cannot answer:

- *«Agregá jabón y leche, cotizá el envío a Leticia y decime cómo puede pagar el cliente.»*
  — runs end to end: freight `$86.435` with Inter Rapidísimo, 7–11 business days, total `$110.835`.
- *«¿Si compro esto por WhatsApp y me lo entregan el jueves santo, hasta cuándo puedo devolverlo?»*
- *«El NIT del cliente es 890903938, ¿cuál es el dígito de verificación?»*
- *«¿Por qué el mismo café cuesta distinto en Medellín y en San Andrés?»*
- *«Prepará el pedido a nombre de la CC 1020304050 pagando con Nequi»* — and watch it stage,
  not sell.

### Checks

```bash
pip install -e ".[dev]"
pytest -q --cov=tendero        # domain + parity tests, coverage floor 85 %
mypy                           # --strict --disallow-any-explicit
ruff check . && ruff format --check .
```

GitHub Actions runs all three, plus a job that loads the real page under a mock
`document.modelContext` and asserts that an agent can grow the tool surface by itself —
the 4 → 7 → 11 progression above is a CI assertion, not a screenshot.

Python 3.12+, `src` layout, frozen slotted dataclasses, no `Any`, money as integer
centavos, never `float`.

## Deploy

Copy `static/` anywhere that serves files. That is the entire deployment.

GitHub Pages does it today at <https://josenobile.github.io/tendero/>; a bucket, a CDN or
`python3 -m http.server` are equally complete deployments. No database, no runtime, no
environment variables, no service to page you at 3 a.m.

---

## Honest notes

- Carrier tariffs, the merchant's identity and product prices are **invented demonstration
  data**. The tax rules, collection ceilings, holiday calendar and check-digit algorithm
  are real, and cited inline.
- The healthy-food taxes of Ley 2277 de 2022 (IBUA on sugary drinks, ICUI on
  ultra-processed food) are **single-stage**: they accrue at the producer or importer, not
  at the counter. Charging them at retail would be wrong, so the catalog flags the affected
  references and explains instead of collecting.
- The PEP (Permiso Especial de Permanencia) was superseded in practice by the PPT (Decreto
  216 de 2021). It is kept because it still appears in pre-2021 customer records and DIAN
  still publishes code 47.
- **Payment runs in Wompi sandbox only — no real money moves.** Ten of the eleven tools
  advise, validate, quote and stage; the eleventh, `confirmar_pago`, can close the sale, but
  only after a human's one-click authorization the agent structurally cannot bypass —
  `confirmar_pago` refuses until an order is staged, a human has sealed it, and `iniciar_pago`
  has issued the sandbox checkout. The human authorizes the sale; the agent executes the
  payment.

## Disclosure

Pre-existing code, third-party dependencies and AI assistance are disclosed in
[`docs/NEW-VS-PREEXISTING.md`](docs/NEW-VS-PREEXISTING.md), as the challenge rules require.

## Licence

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Jose Nobile.
