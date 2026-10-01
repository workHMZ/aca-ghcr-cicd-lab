terraform {
  required_version = "~> 1.15"

  # Configure the Azure Storage account/container/key through `terraform init
  # -backend-config=...`. Keep the existing encrypted remote state during OIDC
  # migration; previous state versions can contain retired client secrets.
  backend "azurerm" {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "5.6.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "3.10.0"
    }
  }
}

provider "azurerm" {
  features {}
}

provider "azuread" {}
