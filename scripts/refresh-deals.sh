#!/usr/bin/env bash
# The weekly routine: fetch this week's deals of every chain, then publish them to the
# AWS demo. With --local, only fetch (no AWS needed).
#
# When: on Tuesday. AH's week runs Monday to Sunday and Lidl's new deals start on
# Monday or Thursday; Jumbo's runs Wednesday to Tuesday, and on a Tuesday its page
# already lists the next week. Any other day works too: a chain whose deals have run
# out is ranked on its last day with deals until the next refresh.
#
# About 170 requests in all (AH ~65, Jumbo ~100, Lidl 1), a few minutes, following the
# scraping policy in PLAN.md §9.4 step 3. Once a week, not more.
set -uo pipefail # not -e: one chain failing must not stop the others being published

# Always from the repository root, so the data lands in ./data and nowhere else.
cd "$(dirname "$0")/.."

publish=true
if [[ "${1:-}" == "--local" ]]; then
  publish=false
fi

# Check the AWS session before asking any supermarket: deals fetched but not
# publishable would mean doing it all again after logging in.
if $publish && ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "Not signed in to AWS: run 'aws login' first, or use --local to only fetch." >&2
  exit 1
fi

echo "==> Fetching this week's deals of every chain"
uv run koopjeskompas fetch-deals
fetched=$? # nonzero when any chain failed; the ones that worked are saved anyway

if $publish; then
  echo "==> Publishing the deals to the demo"
  uv run koopjeskompas publish-deals || exit $?
fi

if [[ $fetched -ne 0 ]]; then
  echo "Some chains failed (see above). Their previous deals stay in use until the" \
    "next refresh; the others are up to date." >&2
  exit 1
fi
echo "==> Done: every chain is up to date."
