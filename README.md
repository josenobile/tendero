# Tendero

> **Shopify's WebMCP tools assume a prepaid card, a street address and a
> self-serve checkout. A Colombian sale is none of those — Tendero registers the
> eight tools a Latin American sale actually requires.**

Built for the OpenAI **WebMCP Challenge**. MIT licensed. Spanish-language
storefront, English documentation.

- **Live storefront:** _(see [Deploy](#deploy) — one file, one process, no build step)_
- **Video:** _(under 3 minutes, walking through the eight tools and the dynamic surface)_

---

## The thesis

WebMCP lets a page hand an AI agent its own tools:

```js
document.modelContext.registerTool({ name, description, inputSchema, execute });
```

The obvious tool set — search the catalog, view a product, add to cart, check
out — is already shipping. It is not neutral. It encodes assumptions that are
true in the United States and false almost everywhere else:

| The assumption | What a Colombian sale actually is |
| --- | --- |
| The buyer has a prepaid card | **Cash on delivery is the dominant rail** outside the big cities — and it has a collection ceiling, partial carrier coverage, and seven municipalities where it does not exist at all |
| A shipping address is just a field | **The tax owed depends on the destination department.** The same coffee costs less in Leticia, and not because of freight |
| Tax is a percentage added at the end | Colombia has **four** VAT treatments, and *exento* and *excluido* are different things in law with different consequences for the seller |
| Checkout is final | The buyer has a statutory **five business day** right of withdrawal, counted against a calendar with 18 public holidays, twelve of which move to Monday |
| Identity is an email address | An electronic invoice is **rejected by the tax authority** without a valid document type and, for a company, a correct NIT check digit |

A field of US developers will not think of these. That is the creativity. They
are real law and real logistics that block real money. That is the impact.

The storefront is **Surtitienda La Milagrosa**, a corner store in Manrique,
Medellín. It is modelled as a corner store on purpose: a Colombian grocery
basket crosses all five tax treatments at once — plantain is *excluido*, milk is
*exento*, coffee is 5 %, soap is 19 %, and the set lunch pays consumption tax
instead of VAT. A seven-line cart already forces five different liquidations.

---

## The eight tools

The first six exist because a specific Colombian rule makes the generic version
wrong. The last two exist because an agent must be able to *build* the order, not
just read it: the cart is browser state, so the tools that write it are
page-only wrappers with no route. Every one is registered with a full JSON
Schema and a description written for an agent to read — the descriptions cite
the statute, because an agent that cannot cite the rule will invent one.

### 1. `buscar_productos` — the price is a function of the destination

Returns each reference with its tax regime *and its shelf price computed for the
destination*. Article 423 of the Estatuto Tributario excludes San Andrés and
Providencia from VAT; article 270 of Ley 223 de 1995 does the same for Amazonas,
Guainía and Vaupés. The same 250 g of Antioquian coffee is `$14.900` in Medellín
and `$14.200` in Leticia. A tool that returns one price is returning a wrong one.

`readOnlyHint` · `untrustedContentHint` (merchant-authored product copy)

### 2. `cotizar_envio` — seven towns where cash on delivery cannot exist

Quotes freight with five carriers and answers the question that actually blocks
the sale: **does this destination accept cash on delivery?** Leticia, Puerto
Nariño, Mitú, Inírida, Puerto Carreño, San Andrés and Providencia have no road.
Freight goes as air cargo, a local agent makes the final delivery, and *no
carrier will collect cash there*. Volumetric weight at the Colombian 6000 factor
with a one-kilo billing floor; declared-value handling fees; per-carrier
collection ceilings.

`readOnlyHint: false` — this is the one tool that **writes**: it fixes the page's
shipping destination. See [the dynamic surface](#the-dynamic-surface).

### 3. `validar_documento_dian` — the check digit that rejects the invoice

Six identity types with their codes from DIAN's electronic-invoicing technical
annex (CC 13, CE 22, NIT 31, PA 41, TI 12, PEP 47), each with its own length and
character rules. For a NIT it verifies the check digit with the real algorithm —
digits weighted right to left by the official prime series, summed modulo 11,
remainder 0 or 1 giving 0 and anything else giving `11 − r` — and **computes it
when the customer did not dictate it**, because a corner-store customer never
knows it. One wrong digit rejects the entire electronic document.

Asserted in tests against genuine Colombian NITs: Bancolombia `890903938-8`,
DIAN itself `800197268-4`, Grupo Éxito `890900608-9`, Servientrega `860512330-3`.

`readOnlyHint`

### 4. `calcular_total_con_iva` — *exento* is not *excluido*

- **19 %** general rate (art. 468 ET)
- **5 %** reduced rate — coffee, flour, pasta, cured meats (art. 468-1 ET)
- **Exento** — zero-rated (art. 477 ET: meat, milk, eggs). The seller **keeps**
  the right to deduct input VAT. The invoice carries a tax line at 0.00 %.
- **Excluido** — outside the tax (art. 424 ET: fresh produce, panela, rice). The
  seller **loses** that right; input VAT becomes cost. No tax line at all.
- **INC 8 %** — prepared food pays consumption tax *instead of* VAT (art. 512-1)

Plus the territorial override that switches VAT off entirely by destination. All
arithmetic is on integer centavos with explicit `ROUND_HALF_UP`, computed **per
line and then summed** — DIAN validates that per-line tax adds up to the document
total, and half a centavo of drift rejects the invoice.

The response also reports how much of the sale keeps the right to deductible
input VAT, which is the practical consequence of the exento/excluido difference:
on the excluded portion the VAT the shop paid its supplier is not recovered — it
becomes cost, and if it is not passed into the price the sale quietly loses
margin.

`readOnlyHint`

### 5. `consultar_derecho_retracto` — five business days, against the real calendar

Article 47 of Ley 1480 de 2011 grants five **business** days from delivery — but
only for distance and non-traditional sales. Buy at the counter and there is no
withdrawal right at all.

The calendar is implemented, not tabulated: Easter from the anonymous Gregorian
algorithm, Maundy Thursday and Good Friday at −3 and −2, and the Emiliani law
(Ley 51 de 1983) moving twelve holidays to the following Monday, with Ascensión,
Corpus Christi and Sagrado Corazón at Easter +43, +64 and +71 — deltas that
already include that shift. Delivered on Maundy Thursday 2026-04-02, the window
closes on 2026-04-10: **five business days is eight calendar days.**

The article's own paragraph carves out perishables, custom-made goods and
already-started services — so an arepa is not returnable, and the tool detects
that from the cart and says *why*.

`readOnlyHint`

### 6. `metodos_de_pago` — rails, not buttons

Evaluates five Colombian rails against this order and **returns the ones that do
not apply, with the reason**, because the useful answer for a customer is not
that cash on delivery is missing but why.

- **Nequi** is a low-value deposit and cannot move more than eight minimum wages
  per operation (Decreto 2555 de 2010)
- **PSE** cannot start without the buyer's bank
- **Cash on delivery** needs physical goods, carrier coverage and a ceiling
- **Card** is the only rail with instalments and the most expensive one

The merchant-side model includes the 1.5 % withholding the card acquirer applies
and the 4x1000 financial-movements tax (art. 870 ET) that every rail eventually
pays. Annually-decreed values (UVT, minimum wage) live in a `ParametrosFiscales`
object rather than inline constants, so the system cannot quietly start a new
year computing last year's ceilings.

`readOnlyHint` · `untrustedContentHint` (carrier-sourced reasons)

### 7. `agregar_al_carrito` — the door to the surface

The cart is page state, not backend state, so the tool that writes it has no
route: it is a thin wrapper over the page's own `agregar(sku, delta)`. Each line
is free text (`consulta`, resolved with the same accent-tolerant search as
`buscar_productos`) or an exact `sku`, plus a quantity. A free-text line that
matches more than one reference is **never guessed**: the tool returns the
candidates and asks the agent to disambiguate; a line that matches nothing comes
back `isError` with the search term named. It returns the recomputed cart, and
it is the first move of the growth mechanic — the first reference moves the page
from rung 0 to rung 1, no human click in between.

`readOnlyHint: false` · `idempotentHint: false` — it writes, and twice is not the same as once.

### 8. `quitar_del_carrito` — the way back out

Removes units of a reference by `sku`; omit `cantidad` to drop the whole line.
It is the exact inverse of `agregar_al_carrito` over the same page function, so
there is no second cart logic to drift, and an empty cart sends the surface back
to rung 0.

`readOnlyHint: false` · `idempotentHint: false`

---

## The dynamic surface

`registerTool` is easy. The interesting part of WebMCP is that the tool set is
**not static** — a page can change what an agent is allowed to do as its own
state changes, and announce it. Tendero uses
`document.modelContext.addEventListener("toolchange", …)` for real, not as
decoration.

The surface has three rungs, and **each gate has a reason, not a rule**:

| Cart state | Tools exposed | Why the others are absent |
| --- | --- | --- |
| **Empty** | `buscar_productos`, `validar_documento_dian`, `agregar_al_carrito`, `quitar_del_carrito` | The other four describe *an order*. With an empty cart they have nothing to operate on, and offering them invites an agent to hallucinate one. The cart writers stay: they are how the order gets built in the first place. |
| **Has items** | + `calcular_total_con_iva`, `consultar_derecho_retracto`, `cotizar_envio` | Now there is an order: it can be liquidated, its withdrawal window computed, and its freight quoted. Payment still cannot be discussed — the rails depend on the municipality. |
| **Destination set** | + `metodos_de_pago` | The rails are a function of the destination. |

Two things make this more than a counter going up:

**The agent moves the surface itself.** The two cart writers and `cotizar_envio`
are the tools marked `readOnlyHint: false`: adding a reference creates the order,
and quoting freight *fixes the page's destination*, which is exactly what a
shopper does when they type their city. So an agent that calls
`agregar_al_carrito` and then `cotizar_envio("Leticia")` walks the page from
rung 0 to rung 2 and `metodos_de_pago` appears for it — no human click in between.

**The description mutates with the state.** When the selected destination is one
of the seven road-less municipalities, `metodos_de_pago` is re-registered with a
description that carries the warning: *no hay vía terrestre, el contra entrega no
existe allí*. When the destination is VAT-excluded, it says so. The tool changes
meaning, not just availability, and every re-registration fires `toolchange`.

The page listens to that event and renders the surface panel from it — the panel
reflects the browser's truth, not the page's own bookkeeping.

### Everything is painted into the DOM

Every `execute` calls the same render function the human buttons call, then
flashes the panel, badges it **🤖 llamado por el agente** and scrolls it into
view. A tool that only returns JSON is invisible in a video and unfalsifiable to
a reviewer. Here, when an agent calls a tool, a person watching the screen sees
the page change.

### Graceful degradation

With no `document.modelContext`, the page shows a banner explaining what is
missing and **stays a working storefront**: search, cart, destination, freight,
VAT, withdrawal window and payment rails all work from the page's own controls,
because the human controls and the agent tools call the same code path.

---

## Architecture

```
static/index.html      one self-contained file: inline CSS + JS, no CDN, no build
       │               registers the eight tools, paints every result
       │               (the two cart writers are page-only: the cart is browser state)
       ▼  POST /api/<tool-name>            ← one route per domain tool, same name
src/tendero/api.py     FastAPI. Translation only. No business logic.
       ▼
src/tendero/domain/    pure rules: no network, no disk, no clock
```

| Module | What it encodes |
| --- | --- |
| `dinero.py` | Integer COP centavos. Explicit `ROUND_HALF_UP`, cash rounding to the 50-peso coin, and a proportional split that cannot lose or invent a centavo. |
| `documento.py` | Six DIAN identity types, their annex codes, and the real NIT check-digit algorithm. |
| `envio.py` | 50 DANE-keyed municipalities in three tiers, five carriers with divergent coverage, volumetric weight, and the seven road-less destinations. |
| `impuesto.py` | The four VAT treatments plus INC, the territorial override, and UBL-shaped tax subtotals. |
| `retracto.py` | Easter, the 18 holidays, the Emiliani shift, business-day arithmetic and the article-47 carve-outs. |
| `pago.py` | Five rails with their regulatory ceilings, and the merchant's real net after commission, withholding and 4x1000. |
| `catalogo.py` | 24 references spanning all five treatments, priced per destination. |

The domain layer knows nothing about HTTP and nothing about WebMCP, so every
rule is unit-tested without starting a server.

---

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn tendero.api:app --reload --port 8000
# open http://127.0.0.1:8000
```

Deep-link straight into the interesting state:

```
http://127.0.0.1:8000/?carrito=ASE-JAB-X3:2,LAC-LEC-1L:3,CAF-TOS-250:1&destino=91001
```

That is a cart with three tax regimes shipping to Leticia: VAT switched off, no
cash on delivery, air-cargo surcharge, and `metodos_de_pago` carrying the
road-less warning in its own description.

### Try it with an agent

Open the page in a browser that exposes WebMCP and ask for something a generic
commerce tool set cannot answer:

- *«Agregá jabón y leche, cotizá el envío a Leticia y decime cómo puede pagar el cliente.»*
- *«¿Si compro esto por WhatsApp y me lo entregan el jueves santo, hasta cuándo puedo devolverlo?»*
- *«El NIT del cliente es 890903938, ¿cuál es el dígito de verificación?»*
- *«¿Por qué el mismo café cuesta distinto en Medellín y en San Andrés?»*

### Checks

```bash
pytest -q --cov=tendero        # domain + HTTP tests, coverage floor 85 %
mypy                           # --strict --disallow-any-explicit
ruff check . && ruff format --check .
```

Python 3.12+, `src` layout, frozen slotted dataclasses, no `Any`, money as
integer centavos, never `float`.

## Deploy

The whole thing is one ASGI app and one static file — no database, no build
step, no external service.

```bash
pip install -e .
uvicorn tendero.api:app --host 0.0.0.0 --port ${PORT:-8000}
```

That command runs unchanged on Fly.io, Render, Railway, Cloud Run or any box
with Python. `GET /health` is the readiness probe. `GET /openapi.json` documents
the six routes.

---

## Honest notes

- Carrier tariffs, the merchant's identity and product prices are **invented
  demonstration data**. The tax rules, collection ceilings, holiday calendar and
  check-digit algorithm are real, and cited inline.
- The healthy-food taxes of Ley 2277 de 2022 (IBUA on sugary drinks, ICUI on
  ultra-processed food) are **single-stage**: they accrue at the producer or
  importer, not at the counter. Charging them at retail would be wrong, so the
  catalog flags the affected references and explains instead of collecting.
- The PEP (Permiso Especial de Permanencia) was superseded in practice by the PPT
  (Decreto 216 de 2021). It is kept because it still appears in pre-2021 customer
  records and DIAN still publishes code 47.
- All eight tools are advisory. None of them takes the customer's money — the human
  still commits the purchase.

## Disclosure

Pre-existing code, third-party dependencies and AI assistance are disclosed in
[`docs/NEW-VS-PREEXISTING.md`](docs/NEW-VS-PREEXISTING.md), as the challenge rules
require.

## Licence

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Jose Nobile.
