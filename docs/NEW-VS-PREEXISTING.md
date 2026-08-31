# New vs. pre-existing code

The WebMCP Challenge requires entrants to disclose which parts of a submission
already existed before the contest and which were written for it. This is that
disclosure.

## Everything in this repository is new

Every line of source in this repository was written for this challenge, from an
empty directory, against the published rules. There is no prior project, no
forked repository, no internal codebase this was extracted from, and no code
copied from another product.

| Path | Status | What it is |
| --- | --- | --- |
| `src/tendero/domain/` | **New** | The pure rules layer: DIAN identity, IVA regimes, freight, the Colombian holiday calendar, the right of withdrawal and the payment rails. No network, no disk, no clock. |
| `src/tendero/api.py` | **New** | FastAPI translation layer. One `POST /api/<name>` per WebMCP tool. Contains no business logic. |
| `static/index.html` | **New** | The storefront and the six `document.modelContext.registerTool` registrations. One self-contained file: inline CSS and JS, no CDN, no build step. |
| `tests/` | **New** | Unit tests for the domain, plus HTTP tests driven by FastAPI's `TestClient`. |
| `README.md`, `docs/`, `LICENSE` | **New** | Documentation and the MIT licence. |

## Pre-existing components

The only pre-existing components are third-party dependencies, all of them
widely used open-source packages installed from PyPI and unmodified:

| Dependency | Licence | Why it is here |
| --- | --- | --- |
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | HTTP routing and OpenAPI generation. |
| [Starlette](https://github.com/encode/starlette) | BSD-3-Clause | The ASGI toolkit FastAPI is built on; also serves the static file. |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | Request/response validation, used through FastAPI. |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | ASGI server for local runs and deployment. |
| [pytest](https://github.com/pytest-dev/pytest), [coverage](https://github.com/nedbat/coveragepy), [mypy](https://github.com/python/mypy), [ruff](https://github.com/astral-sh/ruff), [httpx](https://github.com/encode/httpx) | MIT / Apache-2.0 / BSD | Development only: tests, coverage, type checking, linting. Not shipped at runtime. |

The browser page loads **nothing** from a third party. No CDN script, no remote
font, no analytics, no framework. It is one HTML file with inline CSS and inline
JavaScript, and a test asserts that it stays that way.

## Reference material that is not code

The Colombian rules encoded here come from public legal sources, cited inline in
the code and in the README: the Estatuto Tributario (arts. 423, 424, 437, 468,
468-1, 476, 477, 488, 512-1, 513-2, 513-6, 870, 879), Ley 1480 de 2011 art. 47,
Ley 51 de 1983, Ley 223 de 1995 art. 270, Decreto 2555 de 2010, and the DIAN
electronic-invoicing technical annex for document-type codes. DANE municipality
codes are public reference data. No text was copied from those sources; the rules
were implemented and the articles are cited so a reader can check them.

Carrier tariffs, the merchant's identity and the product prices are **invented
demonstration data**. The NIT check digits are computed with the real algorithm,
so the sample NITs are well-formed, but `900123456-8` is not a real company.

## AI assistance

AI coding assistants were used throughout, which the challenge rules explicitly
permit. All architecture decisions, the domain model, the choice of which six
capabilities to expose, and every legal citation were directed and reviewed by
the author.

## Licence

MIT, see [`LICENSE`](../LICENSE). Copyright (c) 2026 Jose Nobile.
