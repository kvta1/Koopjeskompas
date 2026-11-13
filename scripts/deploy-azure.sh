#!/usr/bin/env bash
# Deploy the whole Azure demo from this laptop, in the order phase 2 did it by hand:
#
#   1. the API's image, built from this commit, to GitHub Container Registry
#   2. the infrastructure with Terraform (infra/azure/), running that image
#   3. the page, built with the API's address, to the Static Web App
#   4. the deal snapshots, to Blob Storage
#   5. a check that the API answers
#
# Once beforehand: az login, docker login ghcr.io (a token with write:packages), and
# scripts/bootstrap-azure-state.sh. Terraform shows its plan and asks before it changes
# anything: read it, then answer yes.
set -euo pipefail

cd "$(dirname "$0")/.."

for tool in az terraform docker npm uv; do
  if ! command -v "$tool" >/dev/null; then
    echo "Missing '$tool': install it first (infra/azure/README.md)." >&2
    exit 1
  fi
done
if ! az account show >/dev/null 2>&1; then
  echo "Not signed in to Azure: run 'az login' first." >&2
  exit 1
fi
# Terraform's Azure provider uses your az login, but wants the subscription named.
ARM_SUBSCRIPTION_ID=$(az account show --query id --output tsv)
export ARM_SUBSCRIPTION_ID

tf() { terraform -chdir=infra/azure "$@"; }

echo "==> 1. The API's image"
# Tagged with the commit, so every deploy says exactly which code runs. Uncommitted
# changes to what goes into the image would make that tag a lie.
if [[ -n "$(git status --porcelain -- Dockerfile .dockerignore pyproject.toml uv.lock README.md koopjeskompas)" ]]; then
  echo "Uncommitted changes in the API's code: commit them first, so the image's" \
    "tag (the commit) matches what's in it." >&2
  exit 1
fi
tag=$(git rev-parse --short HEAD)
image="ghcr.io/kvta1/koopjeskompas-api:$tag"
if docker manifest inspect "$image" >/dev/null 2>&1; then
  echo "$image is already in the registry."
else
  docker build --pull --tag "$image" .
  if ! docker push "$image"; then
    echo "Pushing failed: run 'docker login ghcr.io' (username: your GitHub name," \
      "password: a token with write:packages), then deploy again." >&2
    exit 1
  fi
fi

echo "==> 2. The infrastructure (Terraform)"
tf init -input=false
tf apply -var "image_tag=$tag"
api_url=$(tf output -raw api_url)
page_url=$(tf output -raw page_url)
deals_url=$(tf output -raw deals_container_url)

echo "==> 3. The page"
# The variable on the same line as the build: only then does Vite see it.
(cd frontend && npm ci --silent && VITE_API_BASE_URL="$api_url" npm run build)
if ! grep -q "$api_url" frontend/dist/assets/*.js; then
  echo "The built page doesn't contain $api_url: not deploying it." >&2
  exit 1
fi
# The token only for this one command, never printed or exported. It decides which
# Static Web App receives the files (without it the SWA CLI makes a new one).
(cd frontend && SWA_CLI_DEPLOYMENT_TOKEN="$(tf output -raw static_web_app_api_key)" \
  npx --yes @azure/static-web-apps-cli@2.1.0 deploy ./dist --env production)

echo "==> 4. The deals"
if compgen -G "data/deals/*.json" >/dev/null; then
  if ! uv run koopjeskompas publish-deals --cloud azure --container-url "$deals_url"; then
    echo "Publishing failed. On a first deploy your new role can take a few minutes;" \
      "then run: uv run koopjeskompas publish-deals --cloud azure --container-url $deals_url" >&2
  fi
else
  echo "No snapshots in data/deals/: run 'scripts/refresh-deals.sh --azure'." \
    "Until then the API can't start." >&2
fi

echo "==> 5. Does the API answer?"
# The first request wakes the app (scaled to zero); give it two minutes.
for _ in $(seq 1 24); do
  if curl --silent --fail --max-time 30 "$api_url/api/health" >/dev/null; then
    echo "==> Done."
    echo "    Page: $page_url"
    echo "    API:  $api_url"
    exit 0
  fi
  sleep 5
done
echo "The API doesn't answer $api_url/api/health. Its logs:" \
  "az containerapp logs show --resource-group $(tf output -raw resource_group)" \
  "--name $(tf output -raw api_name) --type console" >&2
exit 1
