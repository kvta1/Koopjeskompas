#!/usr/bin/env bash
# Once, before the first `terraform init` in infra-azure/: create the storage where
# Terraform keeps its state (its record of what it built in Azure).
#
# Why a script and not Terraform: Terraform's state has to exist before Terraform can
# run, so the place it's stored can't be in that state (chicken and egg). This is the
# usual way out: a few CLI commands, run once, and safe to run again: every step checks
# first and changes nothing that's already right.
#
# What it makes, in its own resource group so tearing down the demo never touches it:
#   rg-koopjeskompas-tfstate        resource group, with a lock against deleting it
#   stkoopjeskompastfstate          storage account: no keys (Entra sign-in only), no
#                                   public access, versioning and 7 days of soft delete,
#                                   so an overwritten or deleted state can be restored
#   tfstate                         the container infra-azure/versions.tf points at
#   Storage Blob Data Contributor   for you, so `terraform` (signed in as you) may read
#                                   and write the state
#
# Needs `az login`. The names must match the backend block in infra-azure/versions.tf.
set -euo pipefail

LOCATION=germanywestcentral
GROUP=rg-koopjeskompas-tfstate
ACCOUNT=stkoopjeskompastfstate
CONTAINER=tfstate

if ! az account show >/dev/null 2>&1; then
  echo "Not signed in to Azure: run 'az login' first." >&2
  exit 1
fi

echo "==> Resource group $GROUP"
az group create --name "$GROUP" --location "$LOCATION" \
  --tags project=koopjeskompas purpose=terraform-state --output none

echo "==> Storage account $ACCOUNT"
if ! az storage account show --name "$ACCOUNT" --resource-group "$GROUP" --output none 2>/dev/null; then
  az storage account create --name "$ACCOUNT" --resource-group "$GROUP" \
    --location "$LOCATION" --sku Standard_LRS --kind StorageV2 \
    --min-tls-version TLS1_2 --https-only true \
    --allow-blob-public-access false --allow-shared-key-access false \
    --tags project=koopjeskompas purpose=terraform-state --output none
fi
az storage account blob-service-properties update \
  --account-name "$ACCOUNT" --resource-group "$GROUP" \
  --enable-versioning true \
  --enable-delete-retention true --delete-retention-days 7 \
  --enable-container-delete-retention true --container-delete-retention-days 7 \
  --output none

echo "==> Container $CONTAINER"
# container-rm goes through Azure Resource Manager, like the portal: it needs your
# Owner role, not a data role (which may take minutes to work after the next step).
if [[ "$(az storage container-rm exists --storage-account "$ACCOUNT" \
  --resource-group "$GROUP" --name "$CONTAINER" --query exists --output tsv)" != true ]]; then
  az storage container-rm create --storage-account "$ACCOUNT" \
    --resource-group "$GROUP" --name "$CONTAINER" --public-access off --output none
fi

echo "==> Role: Storage Blob Data Contributor for you"
account_id=$(az storage account show --name "$ACCOUNT" --resource-group "$GROUP" --query id --output tsv)
me=$(az ad signed-in-user show --query id --output tsv)
if [[ -z "$(az role assignment list --assignee "$me" --scope "$account_id" \
  --role "Storage Blob Data Contributor" --query "[].id" --output tsv)" ]]; then
  az role assignment create --assignee-object-id "$me" --assignee-principal-type User \
    --role "Storage Blob Data Contributor" --scope "$account_id" --output none
fi

echo "==> Lock: nobody deletes the state by accident"
# Deleting the group (or the account) now fails until the lock is removed:
#   az lock delete --name keep-terraform-state --resource-group rg-koopjeskompas-tfstate
az lock create --name keep-terraform-state --resource-group "$GROUP" \
  --lock-type CanNotDelete --notes "Terraform state of infra-azure/" --output none

echo "==> Done. A new role can take a few minutes to work; then:"
echo "    terraform -chdir=infra-azure init"
