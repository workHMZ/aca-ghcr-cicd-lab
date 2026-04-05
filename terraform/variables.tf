variable "resource_group_name" {
  description = "Name of the Azure Resource Group"
  type        = string
  default     = "rg-genai-student-jp"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "japaneast"
}

variable "container_app_env_name" {
  description = "Name of the Container Apps Environment"
  type        = string
  default     = "rag-env"
}

variable "container_app_name" {
  description = "Name of the Container App"
  type        = string
  default     = "serverless-rag-api"
}

variable "service_principal_name" {
  description = "Display name of the Service Principal for GitHub Actions"
  type        = string
  default     = "sp-github-rag-deploy"
}
