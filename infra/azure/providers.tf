# How the Azure provider signs in and behaves.
#
# Signing in: with no credentials here, the provider uses your `az login`. Which
# subscription comes from ARM_SUBSCRIPTION_ID (scripts/azure/deploy.sh sets it), so no
# subscription ID is written in the repository.

provider "azurerm" {
  features {}

  # The storage account has Shared Key (account keys) switched off, so the provider
  # has to manage blob containers with your Entra sign-in instead.
  storage_use_azuread = true

  # Since azurerm 5 the provider registers no resource providers by itself. These are
  # the Azure services this code uses; registering one that's already registered is a
  # no-op.
  resource_providers_to_register = [
    "Microsoft.App",                 # Container Apps
    "Microsoft.ManagedIdentity",     # the API's identity
    "Microsoft.OperationalInsights", # Log Analytics
    "Microsoft.Storage",             # Blob Storage
    "Microsoft.Web",                 # Static Web Apps
  ]
}
