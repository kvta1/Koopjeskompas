# Tests for infra/azure/, run with `terraform test` (in CI too).
#
# The azurerm provider is mocked: `apply` here builds nothing in Azure, it fills in
# made-up values for whatever Azure would compute (IDs, host names), so the tests check
# how the resources are wired together, with no account or credentials. The same idea
# as tests/infra/aws/ for the AWS stack.

mock_provider "azurerm" {
  # Values the mock can't make up: Azure checks these are GUIDs.
  mock_data "azurerm_client_config" {
    defaults = {
      object_id       = "00000000-0000-0000-0000-00000000000a"
      tenant_id       = "00000000-0000-0000-0000-00000000000b"
      client_id       = "00000000-0000-0000-0000-00000000000c"
      subscription_id = "00000000-0000-0000-0000-00000000000d"
    }
  }
  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-00000000000d/resourceGroups/rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-api"
      principal_id = "00000000-0000-0000-0000-0000000000a1"
      client_id    = "00000000-0000-0000-0000-0000000000c1"
    }
  }
  # Other resources refer to these by ID, and the provider checks an ID's shape.
  mock_resource "azurerm_storage_account" {
    defaults = {
      id                    = "/subscriptions/00000000-0000-0000-0000-00000000000d/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/stexample"
      primary_blob_endpoint = "https://stexample.blob.core.windows.net/"
    }
  }
  mock_resource "azurerm_storage_container" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-00000000000d/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/stexample/blobServices/default/containers/data"
    }
  }
  mock_resource "azurerm_log_analytics_workspace" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-00000000000d/resourceGroups/rg/providers/Microsoft.OperationalInsights/workspaces/log"
    }
  }
  mock_resource "azurerm_container_app_environment" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-00000000000d/resourceGroups/rg/providers/Microsoft.App/managedEnvironments/cae"
    }
  }
}

variables {
  image_tag = "823ef7a"
}

run "storage_has_no_keys_and_nothing_public" {
  assert {
    condition     = azurerm_storage_account.main.shared_access_key_enabled == false
    error_message = "Account keys must stay off: everyone signs in with Entra and a role."
  }
  assert {
    condition     = azurerm_storage_account.main.allow_nested_items_to_be_public == false
    error_message = "No container may be made public."
  }
  assert {
    condition     = azurerm_storage_container.deals.container_access_type == "private"
    error_message = "The deals container must be private."
  }
}

run "the_api_may_only_read_the_deals_container" {
  assert {
    condition     = azurerm_role_assignment.api_reads_deals.role_definition_name == "Storage Blob Data Reader"
    error_message = "The API needs to read, never to write."
  }
  assert {
    condition     = azurerm_role_assignment.api_reads_deals.scope == azurerm_storage_container.deals.id
    error_message = "The API's role must cover the deals container only, not the whole account."
  }
  assert {
    condition     = azurerm_role_assignment.api_reads_deals.principal_id == azurerm_user_assigned_identity.api.principal_id
    error_message = "The role must go to the API's own identity."
  }
  assert {
    condition     = azurerm_container_app.api.identity[0].identity_ids == toset([azurerm_user_assigned_identity.api.id])
    error_message = "The app must run as that identity."
  }
}

run "the_app_is_told_where_its_deals_identity_and_page_are" {
  # The container's environment variables, as a map: { for e in ... : name => value }.
  assert {
    condition     = { for e in azurerm_container_app.api.template[0].container[0].env : e.name => e.value }["DEALS_CONTAINER_URL"] == output.deals_container_url
    error_message = "The app must read the container publish-deals writes to."
  }
  assert {
    condition     = { for e in azurerm_container_app.api.template[0].container[0].env : e.name => e.value }["AZURE_CLIENT_ID"] == azurerm_user_assigned_identity.api.client_id
    error_message = "With a user-assigned identity, AZURE_CLIENT_ID must name it."
  }
  assert {
    condition     = { for e in azurerm_container_app.api.template[0].container[0].env : e.name => e.value }["CORS_ORIGINS"] == output.page_url
    error_message = "CORS must allow exactly the page's address (https, no trailing slash)."
  }
  assert {
    condition     = azurerm_container_app.api.template[0].container[0].image == "ghcr.io/kvta1/koopjeskompas-api:823ef7a"
    error_message = "The app must run the image built from the given commit."
  }
}

run "probes_ask_the_health_endpoint" {
  assert {
    condition = alltrue([
      azurerm_container_app.api.template[0].container[0].startup_probe[0].path == "/api/health",
      azurerm_container_app.api.template[0].container[0].readiness_probe[0].path == "/api/health",
      azurerm_container_app.api.template[0].container[0].liveness_probe[0].path == "/api/health",
    ])
    error_message = "Every probe must use /api/health, not just check the port."
  }
}

run "costs_are_capped" {
  assert {
    condition     = azurerm_container_app.api.template[0].min_replicas == 0 && azurerm_container_app.api.template[0].max_replicas == 1
    error_message = "Scale to zero, and never above one replica."
  }
  assert {
    condition     = azurerm_log_analytics_workspace.main.daily_quota_gb > 0 && azurerm_log_analytics_workspace.main.daily_quota_gb <= 0.1
    error_message = "Log ingestion needs a small daily cap."
  }
  assert {
    condition     = azurerm_static_web_app.page.sku_tier == "Free"
    error_message = "The page stays on the Free plan."
  }
}

run "the_image_tag_must_be_a_commit" {
  command = plan
  variables {
    image_tag = "latest"
  }
  expect_failures = [var.image_tag]
}
