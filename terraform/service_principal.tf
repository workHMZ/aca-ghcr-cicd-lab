# Service Principal for GitHub Actions

data "azurerm_subscription" "current" {}

resource "azuread_application" "github_actions" {
  display_name = var.service_principal_name
}

resource "azuread_service_principal" "github_actions" {
  client_id = azuread_application.github_actions.client_id
}

# Confirm the exact GitHub OIDC subject before applying; never infer it from names.
resource "azuread_application_federated_identity_credential" "github_stg" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-actions-stg"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = var.github_oidc_subject
}

# Contributor role on the Resource Group
resource "azurerm_role_assignment" "github_actions_contributor" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Contributor"
  principal_id         = azuread_service_principal.github_actions.object_id
}
