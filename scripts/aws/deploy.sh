#!/usr/bin/env bash
# Deploy the whole AWS demo from this laptop: build the API's Lambda zip and the page,
# deploy the CDK stack (infra/aws/), then upload the deal snapshots.
#
# Run `aws login` first. The first time, also bootstrap CDK once (it creates the
# bucket and roles CDK deploys through): cd infra/aws && npx cdk bootstrap
#
# Deploying from the laptop, not GitHub Actions: CI would sign in through OIDC, which
# this AWS project's policies don't allow (PLAN.md §9.3).
set -euo pipefail

cd "$(dirname "$0")/../.."  # the repository root

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "Not signed in to AWS: run 'aws login' first." >&2
  exit 1
fi

echo "==> Building the API's Lambda zip"
scripts/aws/build-lambda.sh

echo "==> Building the page"
(cd frontend && npm ci --silent && npm run build)

echo "==> Deploying the stack"
# CDK shows IAM and security-group changes that widen access and asks before
# applying them ("broadening"); everything else goes ahead.
(cd infra/aws && npm ci --silent && npx cdk deploy --require-approval broadening)

echo "==> Publishing the deal snapshots"
if compgen -G "data/deals/*.json" >/dev/null; then
  uv run koopjeskompas publish-deals
else
  echo "No snapshots in data/deals/: run 'uv run koopjeskompas fetch-deals'," \
    "then 'uv run koopjeskompas publish-deals'. Until then API requests fail (502)." >&2
fi
