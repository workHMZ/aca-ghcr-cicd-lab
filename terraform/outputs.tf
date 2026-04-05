output "container_app_url" {
  description = "FQDN of the Container App"
  value       = "https://${azurerm_container_app.main.ingress[0].fqdn}"
}

output "sp_client_id" {
  description = "Service Principal Client ID"
  value       = azuread_application.github_actions.client_id
}

output "sp_client_secret" {
  description = "Service Principal Password"
  value       = azuread_service_principal_password.github_actions.value
  sensitive   = true
}

output "sp_tenant_id" {
  description = "Azure AD Tenant ID"
  value       = data.azurerm_subscription.current.tenant_id
}

output "sp_subscription_id" {
  description = "Azure Subscription ID"
  value       = data.azurerm_subscription.current.subscription_id
}
