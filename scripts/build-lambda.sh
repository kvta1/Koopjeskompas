#!/usr/bin/env bash
# Build build/lambda.zip: the API and its dependencies, for AWS Lambda's python3.14
# runtime on arm64 (Graviton). Upload it as the function's code; its handler is
# koopjeskompas.api.lambda_handler.handler.
#
# Lambda imports from the top of the zip, so the package and every dependency sit
# there side by side. Dependencies are installed for Lambda's machine, not this
# one: pydantic-core is compiled code, and an x86 or macOS build of it would fail
# to import on Lambda. --only-binary makes a missing Linux arm64 wheel an error
# here instead of a broken function there.
set -euo pipefail

cd "$(dirname "$0")/.."

BUILD=build/lambda
# Amazon Linux 2023, the python3.14 runtime's OS. For an x86_64 function, run with
# PLATFORM=x86_64-manylinux_2_34.
PLATFORM=${PLATFORM:-aarch64-manylinux_2_34}
PYTHON=3.14

rm -rf "$BUILD" build/lambda.zip build/wheel
mkdir -p "$BUILD"

# The locked versions of the runtime dependencies (no dependency groups: no dev or
# infrastructure tools), with hashes, so the zip holds exactly what the tests ran against.
uv export --frozen --no-default-groups --no-emit-project --output-file build/requirements.txt --quiet

uv pip install --quiet --target "$BUILD" --requirements build/requirements.txt \
  --python-platform "$PLATFORM" --python-version "$PYTHON" --only-binary :all:

# The package itself, built as a wheel so its data files (the store list) come along.
uv build --wheel --out-dir build/wheel --quiet
uv pip install --quiet --target "$BUILD" --no-deps build/wheel/*.whl \
  --python-platform "$PLATFORM" --python-version "$PYTHON"

# Python's own zipfile module: no dependency on the zip tool.
uv run --no-sync python -m zipfile --create build/lambda.zip "$BUILD"/*

echo "Built build/lambda.zip ($(du -h build/lambda.zip | cut -f1))"
