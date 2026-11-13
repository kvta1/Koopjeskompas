# The API: the container image from GitHub Container Registry, run by Container Apps,
# reading the deals with a managed identity and logging to Log Analytics.

# --- Identity --------------------------------------------------------------------
#
# User-assigned, not system-assigned as in the portal. A system-assigned identity is
# born with the app, so its role can only be granted after the app exists: the first
# start always failed (phase 2, step 6). This identity is a resource of its own, so it
# and its role exist before the app's first start.

resource "azurerm_user_assigned_identity" "api" {
  name                = local.names.identity
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

# Least privilege: read-only, and only the deals container, not the whole account.
resource "azurerm_role_assignment" "api_reads_deals" {
  scope                = azurerm_storage_container.deals.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
  principal_type       = "ServicePrincipal" # skips a lookup that can fail for a brand-new identity
}

# --- Logs ------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "main" {
  name                = local.names.log_workspace
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018" # pay per GB ingested; the first 5 GB a month are free
  retention_in_days   = 30          # the minimum, and free
  daily_quota_gb      = 0.1         # a cap: a crash loop can't log up a bill
  tags                = local.tags
}

# --- Container Apps environment ----------------------------------------------------
#
# The shared "cluster" the app runs in (it is Kubernetes underneath, managed by Azure).

resource "azurerm_container_app_environment" "main" {
  name                = local.names.environment
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  # Keep the console and system logs in the workspace, so a crash can be read
  # afterwards (phase 2: without this, only the live log stream had them).
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  # Pay per use, scale to zero: as the portal sets up a new environment.
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }

  tags = local.tags
}

# --- The app -----------------------------------------------------------------------

resource "azurerm_container_app" "api" {
  name                         = local.names.container_app
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single" # one revision at a time; a new one replaces the old

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  template {
    # Scale to zero without requests (nothing to pay), and never above one replica, so
    # a burst of traffic can't run up costs.
    min_replicas = 0
    max_replicas = 1

    container {
      name   = local.names.api_container_name
      image  = "${var.image}:${var.image_tag}"
      cpu    = 0.25 # the smallest size; cpu and memory come in fixed pairs
      memory = "0.5Gi"

      # Settings read by koopjeskompas/api/container.py.
      env {
        name  = "DEALS_CONTAINER_URL"
        value = "${azurerm_storage_account.main.primary_blob_endpoint}${azurerm_storage_container.deals.name}"
      }
      env {
        # Which identity DefaultAzureCredential should use: with a user-assigned one,
        # the app has to name it (a system-assigned one is found without this).
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.api.client_id
      }
      env {
        # The page, on its own domain, may call the API (CORS).
        name  = "CORS_ORIGINS"
        value = "https://${azurerm_static_web_app.page.default_host_name}"
      }

      # Probes on the app's health endpoint, rather than Azure's default of "the port
      # is open". Startup: the app downloads the deals before it listens, so allow it
      # up to a minute (30 × 2 s). Then readiness (may it get traffic?) and liveness
      # (should it be restarted?) every 10 s.
      startup_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/api/health"
        interval_seconds        = 2
        failure_count_threshold = 30
      }
      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/api/health"
      }
      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/api/health"
      }
    }
  }

  # A public HTTPS address; Azure terminates TLS and forwards to port 8000.
  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = local.tags

  # Not before the identity may read the deals, or the first start fails. (A new role
  # can still take a few minutes to work everywhere; the app then starts on the next
  # request.)
  depends_on = [azurerm_role_assignment.api_reads_deals]
}
