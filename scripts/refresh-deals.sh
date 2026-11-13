#!/usr/bin/env bash
# The weekly routine: fetch this week's deals of every chain, then publish them to the
# AWS demo, and with --azure to the Azure demo too. With --local, only fetch (no cloud
# needed).
#
#   scripts/refresh-deals.sh            fetch, publish to AWS        (aws login)
#   scripts/refresh-deals.sh --azure    fetch, publish to AWS + Azure (aws login, az login)
#   scripts/refresh-deals.sh --local    fetch only
#
# When: on Tuesday. AH's week runs Monday to Sunday and Lidl's new deals start on
# Monday or Thursday; Jumbo's runs Wednesday to Tuesday, and on a Tuesday its page
# already lists the next week. Any other day works too: a chain whose deals have run
# out is ranked on its last day with deals until the next refresh.
#
# About 170 requests in all (AH ~65, Jumbo ~100, Lidl 1), a few minutes, following the
# scraping policy in PLAN.md §9.4 step 3. Once a week, not more.
set -uo pipefail # not -e: one chain or cloud failing must not stop the others

# Always from the repository root, so the data lands in ./data and nowhere else.
cd "$(dirname "$0")/.."

aws=true
azure=false
for arg in "$@"; do
  case "$arg" in
    --local) aws=false ;;
    --azure) azure=true ;;
    *)
      echo "Unknown option: $arg (use --azure or --local)" >&2
      exit 2
      ;;
  esac
done
if ! $aws && $azure; then
  echo "--local only fetches; leave out --azure." >&2
  exit 2
fi

# Check every cloud before asking any supermarket: deals fetched but not publishable
# would mean doing it all again after logging in.
if $aws && ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "Not signed in to AWS: run 'aws login' first, or use --local to only fetch." >&2
  exit 1
fi
if $azure; then
  if ! az account show >/dev/null 2>&1; then
    echo "Not signed in to Azure: run 'az login' first." >&2
    exit 1
  fi
  # Where the Azure demo keeps its deals, as Terraform built it (infra/azure/).
  if ! container_url=$(terraform -chdir=infra/azure output -raw deals_container_url 2>/dev/null); then
    echo "Can't read the Azure demo's storage from Terraform: deploy it first" \
      "(scripts/azure/deploy.sh)." >&2
    exit 1
  fi
fi

echo "==> Fetching this week's deals of every chain"
uv run koopjeskompas fetch-deals
fetched=$? # nonzero when any chain failed; the ones that worked are saved anyway

published=0
if $aws; then
  echo "==> Publishing the deals to the AWS demo"
  uv run koopjeskompas publish-deals || published=1
fi
if $azure; then
  echo "==> Publishing the deals to the Azure demo"
  uv run koopjeskompas publish-deals --cloud azure --container-url "$container_url" ||
    published=1
fi

if [[ $published -ne 0 ]]; then
  echo "Publishing failed (see above): that demo keeps last week's deals." >&2
  exit 1
fi
if [[ $fetched -ne 0 ]]; then
  echo "Some chains failed (see above). Their previous deals stay in use until the" \
    "next refresh; the others are up to date." >&2
  exit 1
fi
echo "==> Done: every chain is up to date."
