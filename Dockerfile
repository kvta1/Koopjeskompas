# The web API as a container image, for Azure Container Apps (or any container host).
# The same app as the AWS Lambda; see koopjeskompas/api/container.py for its settings.
#
#   docker build -t koopjeskompas-api .
#   docker run --rm -p 8000:8000 -v "$PWD/data:/data:ro" koopjeskompas-api
#
# Two stages: the first installs everything with uv, the second copies only the
# result. The final image has no uv, no source tree and no tests: smaller, and less in
# it that could have a vulnerability.

# --- build ---------------------------------------------------------------------
FROM python:3.14-slim AS build

# uv as a single binary from its official image, at the version the repo uses.
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /bin/uv

# Compile to bytecode now rather than at every start; copy files rather than link
# them (the cache isn't kept); use the image's Python rather than downloading one.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# The dependencies first, on their own: Docker caches each step, so a code change
# doesn't reinstall them. --frozen: exactly uv.lock, as tested. Only the `azure`
# group: no dev tools, no CDK.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group azure --no-install-project

# Then the package itself, installed as a copy (not editable), so the final image
# needs no source tree. README.md: pyproject.toml names it as the package's readme.
COPY README.md ./
COPY koopjeskompas ./koopjeskompas
RUN uv sync --frozen --no-default-groups --group azure --no-editable

# --- run -----------------------------------------------------------------------
FROM python:3.14-slim

# Not root: if the app were ever broken into, the attacker shouldn't own the container.
RUN useradd --system --uid 10001 --no-create-home app

COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1

USER 10001
EXPOSE 8000

# For `docker run` and Docker Compose. Azure Container Apps ignores this and uses its
# own probes, configured on the app (phase 2), against the same endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]

# --factory: uvicorn calls create_container_app() once, when the container starts.
# 0.0.0.0: listen on every interface, or nothing outside the container reaches it.
CMD ["uvicorn", "--factory", "koopjeskompas.api.container:create_container_app", \
     "--host", "0.0.0.0", "--port", "8000"]
