# The page: the built frontend (frontend/dist), served worldwide by Static Web Apps.
#
# Terraform makes the empty site; scripts/deploy-azure.sh uploads the files with the
# SWA CLI and the deployment token from outputs.tf. The site and its contents have
# different lifecycles: the files change with every deploy, the site almost never.

resource "azurerm_static_web_app" "page" {
  name                = local.names.static_web_app
  resource_group_name = azurerm_resource_group.main.name
  location            = var.page_location
  sku_tier            = "Free"
  sku_size            = "Free"

  # Preview environments are for pull requests deployed from GitHub; not used.
  preview_environments_enabled = false

  tags = local.tags
}
