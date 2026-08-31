# Tendero, served behind Jose's existing Cloudflare tunnel.
#
# WHY a container rather than a cloud service: the WebMCP challenge requires only a
# "working live URL reachable in ChatGPT's browser" — it imposes no hosting provider.
# This machine is always on and already fronted by cloudflared on `proxy-net`, so the
# tunnel gives a real public HTTPS URL with no third-party account.
#
# (The Google contest is different and this will NOT work there: it mandates a Google
# Cloud service — Cloud Run, Firestore, GKE, Pub/Sub — and a tunnel satisfies none.)

FROM python:3.12-slim

# Non-root: the tunnel exposes this to the public internet, so the process should not
# be able to write to its own code.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin tendero

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY static ./static

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir . uvicorn[standard]

# The package is installed into site-packages, so the static directory is not a
# sibling of the code at runtime. Declaring it removes the guesswork entirely.
ENV TENDERO_STATIC_DIR=/app/static

USER 10001

# 8000 inside the container; the tunnel maps the public hostname to it, so no host
# port is published and nothing is reachable except through Cloudflare.
EXPOSE 8000

# One worker: the domain is pure and stateless, and a single process keeps the
# footprint small on a box that also runs a 27B model and ~20 other services.
CMD ["uvicorn", "tendero.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
