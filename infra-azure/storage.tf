# Blob Storage for the weekly deals: `publish-deals --cloud azure` writes
# deals/<chain>.json into the container, the API reads them when it starts.

resource "azurerm_storage_account" "main" {
  name                     = local.names.storage_account
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS" # three copies in one datacentre: enough for data we can fetch again

  # Nobody signs in with the account's keys: only with an Entra identity and a role
  # (you with az login, the API with its managed identity). A key can leak; a role
  # can be scoped to one container and taken away.
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true # the portal uses your sign-in too

  allow_nested_items_to_be_public = false # no container can be made public
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true

  tags = local.tags
}

resource "azurerm_storage_container" "deals" {
  name                  = local.names.deals_container
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

# Whoever runs Terraform (you, signed in with az login) may upload the deals.
data "azurerm_client_config" "current" {}

resource "azurerm_role_assignment" "deployer_writes_deals" {
  scope                = azurerm_storage_container.deals.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}
