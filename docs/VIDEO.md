# Demo video — script

**Hard constraints from the rules:** under 3 minutes · public YouTube · **with audio** ·
"a clear demo … of what you built and how you used WebMCP".

**Judging context this script is written against:** four equally-weighted criteria —
WebMCP Leverage, Execution, Potential Impact, Creativity & Ambition. The audit found the
project's weakest axes are Execution (was: nothing deployed) and Potential Impact (the
case is argued in prose rather than demonstrated). So the video must *show* the law
biting, not narrate it.

**Language: English narration.** Three independent judges flagged that the entire
differentiator — Colombian tax and logistics law — is currently argued in a Spanish UI,
and a judge who cannot read Spanish falls back to "another storefront". The store stays
Spanish (it is a Medellín corner store; that is the point), the narration carries the
meaning.

---

## 0:00–0:15 — The thesis, before anything else

> "Every WebMCP commerce demo registers the same four tools: search, view, add to cart,
> check out. That tool set isn't neutral. It assumes a prepaid card, a street address,
> and a self-serve checkout — and outside the US, all three are wrong."

Screen: the deployed page, hero line visible.

## 0:15–0:35 — One prompt, and the surface grows

Screen: agent panel. Paste **one** prompt and let it run uninterrupted:

> «Agregá jabón y leche, cotizá el envío a Leticia y decime cómo puede pagar el cliente»

> "The page starts by offering the agent two tools. It adds the products itself — and the
> page hands it four more, because with a cart and a destination there are now four more
> things that make sense."

Screen: the tool counter going 2 → 8. This is the single most important shot in the video:
it is the WebMCP Leverage criterion, demonstrated rather than claimed.

## 0:35–1:05 — The law biting, three times

> "Leticia is in Amazonas. Watch three things change."

1. **Tax** — the same basket, a different total, because the destination department
   changes what is owed. Not freight. Tax.
2. **Payment** — `metodos_de_pago` has *rewritten its own description* to warn there is no
   road access and the basket contains VAT-excluded lines. The agent re-reads its rules
   mid-conversation.
3. **The basket itself** — plantain is *excluido*, milk is *exento*, coffee 5%, soap 19%,
   the set lunch pays consumption tax instead of VAT. Five treatments, one cart.

> "*Exento* and *excluido* both translate to 'no VAT charged'. In Colombian law they are
> different states with different consequences for the seller. A generic tool set cannot
> know that. This page does."

## 1:05–1:30 — The two tools nobody else has

- `validar_documento_dian` — an invoice is **rejected by the tax authority** if the NIT
  check digit is wrong. Show a real rejection, then a valid one.
- `consultar_derecho_retracto` — five *business* days, against a calendar with 18 public
  holidays, twelve of which shift to Monday. Show the window landing on a different date
  than a naive +5 would give.

> "These have no analogue in any storefront demo, because they aren't commerce features.
> They're the law."

## 1:30–2:00 — Humans and agents, together

Screen: `confirmar_pedido`. The agent stages a complete order — and stops.

> "The agent assembles the order. It does not commit it. The page renders what will
> happen and waits for a human click. That's the division of labour this should have:
> the agent knows the catalogue and the arithmetic, the human takes responsibility for
> the sale."

Human clicks. The order artifact appears.

## 2:00–2:25 — Why it is trustworthy

Screen: `tests/parity/` running.

> "The Colombian rule engine runs in the page, in JavaScript, so the page owns its own
> capabilities. A differential test suite pins that JavaScript to a Python reference
> implementation — if any value diverges, or even an error message, CI fails."

Screen: every agent-touched panel badged **"🤖 llamado por el agente"**.

> "And every tool call paints the page, so a human watching sees exactly what the agent
> did."

## 2:25–2:45 — Close

> "Tendero — the tools a Colombian sale actually needs. The code is MIT, the rules are
> cited to the statute, and it's live at the link below."

Screen: live URL + repo URL held on screen for the final three seconds.

---

## Recording notes

- Record against the **deployed** URL, never localhost — judges must see the artifact they
  can open.
- One take per segment, full screen, no cuts inside the agent run (a cut there reads as a
  hidden failure).
- Burn subtitles: the store UI is Spanish and the narration is English.
- **Verify it plays logged-out** before submitting. An unlisted or private video fails the
  requirement.
- Keep it under 2:50 to leave margin against the 3-minute cap.
