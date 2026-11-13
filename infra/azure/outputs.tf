# What the deploy script and you need after an apply: terraform output <name>.

output "page_url" {
  description = "The web page."
  value       = "https://${azurerm_static_web_app.page.default_host_name}"
}

output "api_url" {
  description = "The API: the app's own address, which follows every new revision (never a revision's address)."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "deals_container_url" {
  description = "Where publish-deals --cloud azure uploads the deals."
  value       = "${azurerm_storage_account.main.primary_blob_endpoint}${azurerm_storage_container.deals.name}"
}

output "resource_group" {
  description = "Everything of the demo is in here."
  value       = azurerm_resource_group.main.name
}

output "static_web_app_api_key" {
  description = "The page's deployment token, for the SWA CLI. A password: read it with terraform output -raw, never print it."
  value       = azurerm_static_web_app.page.api_key
  sensitive   = true # hidden in plan and apply output (but in the state: keep that private)
}

output "api_name" {
  description = "The Container App's name, for az containerapp commands (logs, revisions)."
  value       = azurerm_container_app.api.name
}
