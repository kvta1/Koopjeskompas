#!/usr/bin/env bash
# Build build/lambda.zip: the API and its dependencies, for AWS Lambda's python3.14
# runtime on arm64 (Graviton). Upload it as the function's code; its handler is
# koopjeskompas.cloud.aws.lambda_handler.handler.
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
# uv notes the install time in the package's metadata (uv_cache.json, also listed in
# RECORD). The Lambda never reads it, and it would make every zip different.
rm "$BUILD"/koopjeskompas-*.dist-info/uv_cache.json
sed -i '/uv_cache\.json/d' "$BUILD"/koopjeskompas-*.dist-info/RECORD

# A reproducible zip: the same code gives byte-for-byte the same file. Entries are
# sorted and get a fixed timestamp and permissions instead of each file's own, which
# change with every install. Otherwise every deploy would upload a "new" 20 MB zip
# and replace the function, even when nothing changed.
uv run --no-sync python - "$BUILD" build/lambda.zip <<'PY'
import sys
import zipfile
from pathlib import Path

source, target = Path(sys.argv[1]), sys.argv[2]
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        entry = zipfile.ZipInfo(str(path.relative_to(source)), date_time=(1980, 1, 1, 0, 0, 0))
        entry.external_attr = 0o644 << 16  # rw-r--r--: readable by the Lambda runtime
        entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, path.read_bytes())
PY

echo "Built build/lambda.zip ($(du -h build/lambda.zip | cut -f1))"
