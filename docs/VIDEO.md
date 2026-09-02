# Demo video — script

**Hard constraints from the rules:** under 3 minutes · public YouTube · **with audio** ·
"a clear demo … of what you built and how you used WebMCP".

**Target runtime 2:45** (cap is 3:00 — leave 15 s of margin for the upload's rounding
and for a title card if one is added later).

**Language: English narration, Spanish UI.** The entire differentiator — Colombian tax
and logistics law — lives in a Spanish interface. A judge who cannot read Spanish falls
back to "another storefront" in four seconds. The store stays Spanish (it is a Manrique
corner store; that is the point); the narration carries the meaning; the subtitles are
burned in.

**Every segment is mapped to one of the four equally-weighted criteria.** Nothing in this
script is narrated that is not simultaneously visible on screen. The organizers' own two
reference demos are both storefronts, so the video's first job — inside twelve seconds —
is to establish that this is not one.

**Word budget:** ~165 words/minute → ~450 words of narration total. Per-segment counts are
given; if a take runs long, cut words, never shots.

---

## 0:00–0:12 — The thesis, before anything else
**Criterion: Creativity & Ambition** — say the novel idea before the judge decides what
this is.

Screen: the deployed page on load. Header pill reads **`nivel 0: carrito vacío`**; the
WebMCP panel sub-header reads **`4 de 9 registradas`**.

> "Every WebMCP commerce demo registers the same four tools: search, view, add to cart,
> check out. That tool set is not neutral. It assumes a prepaid card, a street address and
> a self-serve checkout — and outside the United States, all three are wrong. This page
> registers the nine tools a Colombian sale actually needs."

*(48 words · ~12 s)*

---

## 0:12–0:48 — One prompt. No clicks. 4 → 7 → 9.
**Criterion: WebMCP Leverage.** **This is the single most important shot in the video.**
Do not cut inside it — a cut here reads as a hidden failure.

Screen: the agent panel. Paste **one** prompt and let it run uninterrupted, hands off the
mouse:

> «Agregá jabón y leche, cotizá el envío a Leticia y decime cómo puede pagar el cliente»

Keep the **WebMCP surface panel visible in frame the whole time**. What the camera must
catch, in order, with no human input between them:

| moment | on screen |
| --- | --- |
| before | `4 de 9 registradas` · stepper segment 1 lit · `nivel 0: carrito vacío` |
| agent calls `agregar_al_carrito` (free text "jabón", "leche" → SKUs) | **`7 de 9`** · segment 2 lit · `nivel 1: carrito con productos` |
| agent calls `cotizar_envio` for Leticia | **`9 de 9`** · segment 3 lit · `nivel 2: carrito + destino` |

> "I paste one sentence and then take my hands off. The page starts by offering the agent
> four tools. The agent adds the products itself — and the page hands it three more,
> because now there is an order to tax, to quote and to return. It quotes freight to
> Leticia, in the Amazon, and the last two appear. Four, seven, nine — and I never
> clicked. The agent walked the page up its own ladder."

*(72 words · ~26 s, leaving ~10 s of silence for the counter to move on screen)*

Then, without leaving the panel:

> "And `metodos_de_pago` did not just appear — it appeared with its description rewritten
> for a town with no road. Re-registering fires `toolchange`, so the agent re-reads its
> rules mid-conversation instead of carrying a stale copy."

*(41 words · ~10 s)* — hover the tool card so the mutated description is legible.

---

## 0:48–1:18 — The law biting, twice, in one basket
**Criterion: Potential Impact** — the case is *shown*, not argued.

**Bite 1 — five tax treatments in one cart.** Screen: the VAT panel, line by line.

> "One corner-store basket. Plantain is *excluido*. Milk is *exento*. Coffee pays five
> percent, soap nineteen, and the set lunch pays consumption tax instead of VAT. Both
> *exento* and *excluido* translate to 'no VAT charged' — in Colombian law they are
> different states, and on the excluded lines the shop's own input VAT stops being
> recoverable and silently becomes cost. A generic `checkout` tool cannot know that.
> This page does."

*(69 words · ~17 s)*

**Bite 2 — the payment rail that is refused.** Screen: `metodos_de_pago`, the rejected
option with its reason legible.

> "And cash on delivery — the dominant rail in Colombia — is *refused* here, in writing:
> Leticia has air access only, so no carrier will collect cash there. The useful answer
> is not that the option is missing. It is why."

*(45 words · ~13 s)*

---

## 1:18–1:45 — The tool no storefront has
**Criterion: Potential Impact / Creativity.**

Screen: `validar_documento_dian`, two calls back to back.

- Type the NIT **900123456-0** → the page answers
  **`INVÁLIDO: dígito de verificación incorrecto… se recibió 0, corresponde 8`**.
- Then the valid form, accepted.

> "An electronic invoice is rejected by the tax authority if a company's NIT check digit
> is wrong. One digit. The tool runs the real algorithm — and computes the digit when the
> customer doesn't know it, which at a corner-store counter is always. This isn't a
> commerce feature. It's the law, and it's the difference between a sale and a rejected
> document."

*(64 words · ~19 s)*

---

## 1:45–2:20 — The agent stops. A human commits.
**Criterion: Execution + the challenge theme** — "humans and agents interact, collaborate
and create together". **This is the closing shot; frame it deliberately.**

Screen: the order panel after `confirmar_pedido`. Two badges are legible before anyone
touches anything:

- **🤖 preparado por el agente**
- **⏳ esperando aprobación humana**

…above the line **«Nada quedó comprometido»** and the button **`Confirmar pedido`**.

> "The agent assembles the whole order — the lines, the tax, the freight, the payment
> ceiling, the withdrawal deadline — and then it stops. It stages. It does not commit.
> Nothing has been charged and nothing has shipped."

*(41 words · ~12 s)*

Now the **only human click in the entire video**. Keep the cursor visible moving to the
button; do not cut.

Screen: the panel repaints to the single badge
**🤖 preparado por el agente · ✋ aprobado por vos**, with the seal
**`PEDIDO SLM-20260902-9026`** and its approval timestamp.

> "That click is a human action, not a tool. The agent knew the catalogue and the
> arithmetic. The person took responsibility for the sale. That's the division of labour
> the open web should ship with — and the seal records the exact moment a human took it."

*(48 words · ~15 s)*

---

## 2:20–2:36 — Why any of it can be trusted
**Criterion: Execution.**

Screen: split or quick pan — `static/dominio.js` beside `tests/parity/`, then the green
GitHub Actions run.

> "The Colombian rule engine runs inside the page, in JavaScript, so the page owns its own
> capabilities — there is no backend at runtime. A differential suite pins that JavaScript
> to a Python reference implementation: if any value diverges, or even an error message,
> CI fails. And CI itself loads this page and proves an agent can grow the surface."

*(59 words · ~16 s)*

Screen (2 s, no narration): a panel badged **🤖 llamado por el agente** — every tool call
paints the page, so a human watching sees exactly what the agent did.

---

## 2:36–2:45 — Close

> "Tendero. Nine tools, the rules cited to the statute, MIT licensed, live now."

*(13 words · ~5 s)*

Screen: live URL and repo URL held, large and static, for the final four seconds.
No music sting over the URLs — legibility beats polish.

---

## Recording checklist

Record in this order; tick each box before moving on.

**Before the first take**
- [ ] Record against the **deployed URL** — `https://josenobile.github.io/tendero/`. Never
      `localhost`, never a `file://` path. Judges must see the artifact they can open, and
      a localhost bar in frame reads as "not really shipped".
- [ ] Browser fully **logged out / clean profile**, no extensions bar, no bookmarks bar, no
      personal tabs.
- [ ] **Reset page state** between takes (fresh load, empty cart) so the counter genuinely
      starts at `4 de 9`.
- [ ] Zoom the browser so `sub-superficie` (`N de 9 registradas`), the level pill and the
      tool descriptions are **readable at 720p** — assume the judge does not full-screen it.
- [ ] Console open? **No.** Zero console errors is a fact for the README, not the video;
      an open devtools panel steals the frame from the counter.

**Per segment**
- [ ] **One take per segment, full screen, no cuts inside a take.** Cuts happen only *between*
      the numbered segments above.
- [ ] Absolutely **no cut inside 0:12–0:48**. That segment must be visibly continuous from
      the paste to `9 de 9`, or the whole WebMCP-Leverage claim is unproven.
- [ ] **No cut between the staged order and the human click** at 1:45–2:20.
- [ ] Hands off the mouse during the agent run — if the cursor twitches, re-shoot.

**After**
- [ ] **Burn subtitles** (open-caption, not a YouTube track): the UI is Spanish, the
      narration is English, and a judge scrubbing without audio must still follow.
- [ ] Audio present and audible on the whole timeline — the rules require audio, and a
      silent screencast is a disqualification risk, not a style choice.
- [ ] Total runtime **≤ 2:50**. Check the final export, not the timeline estimate.
- [ ] Upload **Public** (not Unlisted, not Private) and **verify it plays logged-out** in a
      private window before pasting the link into the submission.
- [ ] Title and description carry the live URL and the repo URL as plain text links.

---

## Facts to re-verify on camera before recording

These are asserted in `README.md` but were **not** re-measured in the browser pass, so do
not narrate a number that the screen does not show:

- The withdrawal-window example (delivered Maundy Thursday 2026-04-02 → closes 2026-04-10,
  "five business days is eight calendar days") — currently *not* narrated; if you add it,
  read the date off the panel.
- The per-destination shelf price (`$14.900` Medellín vs `$14.200` Leticia) — shown only if
  the catalogue panel is on screen at the time.
- "18 public holidays, twelve of which shift to Monday" — a repo claim, not a screen claim.
- The freight figures from the demo prompt (Inter Rapidísimo, 7–11 business days,
  `$127.025` freight, `$175.825` total) are stable but destination- and cart-dependent:
  narrate them only if the frame shows them, or keep the narration qualitative as written
  above.
- The order seal number is generated per approval — `SLM-20260902-9026` is the measured
  example, **not** a constant. Do not narrate the number; let the screen show whatever it
  seals.
