terraform {
  required_version = "~> 1.15.0"

  # Configure the Azure Storage account/container/key through `terraform init
  # -backend-config=...`. This prevents the service-principal password resource
  # from silently landing in an unencrypted local state file.
  backend "azurerm" {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "4.81.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "3.9.0"
    }
  }
}

provider "azurerm" {
  features {}
}

provider "azuread" {}
