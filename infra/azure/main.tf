# The Azure demo, as built by hand in phase 2 of the Azure plan, now as code:
#
#   main.tf      names, tags and the resource group that holds everything
#   storage.tf   Blob Storage for the weekly deals
#   api.tf       the API: identity, logs, Container Apps environment and app
#   page.tf      the page: a Static Web App
#   outputs.tf   what the deploy script and you need afterwards
#
# Terraform reads all .tf files in this folder as one; the split is only for people.

locals {
  # Names follow Microsoft's suggested abbreviations (rg-, st, ca-, ...) and end in the
  # environment, so a second copy (say "test") gets its own names.
  names = {
    resource_group     = "rg-koopjeskompas-${var.environment}"
    storage_account    = "stkoopjeskompas${var.environment}" # lowercase letters and digits only, unique in all of Azure
    identity           = "id-koopjeskompas-api-${var.environment}"
    log_workspace      = "log-koopjeskompas-${var.environment}"
    environment        = "cae-koopjeskompas-${var.environment}"
    container_app      = "ca-koopjeskompas-api-${var.environment}"
    static_web_app     = "stapp-koopjeskompas-${var.environment}"
    deals_container    = "data"
    api_container_name = "api"
  }

  # On every resource, so the portal and the bill can be filtered by them.
  tags = {
    project     = "koopjeskompas"
    environment = var.environment
    managed-by  = "terraform" # a hint not to change it by hand in the portal
  }
}

resource "azurerm_resource_group" "main" {
  name     = local.names.resource_group
  location = var.location
  tags     = local.tags
}
