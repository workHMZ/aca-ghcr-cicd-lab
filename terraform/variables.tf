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

variable "container_cpu" {
  description = "CPU cores allocated to the application container"
  type        = number
  default     = 1

  validation {
    condition     = var.container_cpu > 0
    error_message = "container_cpu must be greater than zero."
  }
}

variable "container_memory" {
  description = "Memory allocated to the application container"
  type        = string
  default     = "2Gi"

  validation {
    condition     = can(regex("^[1-9][0-9]*(Mi|Gi)$", var.container_memory))
    error_message = "container_memory must use an Azure Container Apps value such as 2Gi."
  }
}

variable "azure_search_endpoint" {
  description = "Azure AI Search endpoint used by the application"
  type        = string
  default     = "https://rg-genai-student-jp.search.windows.net"
}

variable "azure_search_index_name" {
  description = "Azure AI Search index for the 3.0 embedding space"
  type        = string
  default     = "ragdocs-v3"
}

variable "openai_model" {
  description = "OpenAI model used by the application"
  type        = string
  default     = "gpt-5.6-terra"
}

variable "openai_reasoning_effort" {
  description = "OpenAI reasoning effort used by the application"
  type        = string
  default     = "low"

  validation {
    condition     = contains(["none", "low", "medium", "high", "xhigh", "max"], var.openai_reasoning_effort)
    error_message = "openai_reasoning_effort must be a supported reasoning effort."
  }
}

variable "embedding_model" {
  description = "Pinned Hugging Face embedding model identifier"
  type        = string
  default     = "intfloat/multilingual-e5-small"
}

variable "embedding_model_revision" {
  description = "Immutable Hugging Face embedding model revision"
  type        = string
  default     = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
}

variable "environment_name" {
  description = "Deployment environment name"
  type        = string
  default     = "stg"
}

variable "datadog_site" {
  description = "Datadog site used by the application and Agent"
  type        = string
  default     = "us5.datadoghq.com"
}

variable "datadog_environment" {
  description = "Datadog environment tag"
  type        = string
  default     = "stg"
}

variable "datadog_service" {
  description = "Datadog service tag"
  type        = string
  default     = "serverless-rag-api"
}

variable "enable_datadog_sidecar" {
  description = "Run the Datadog Agent as a sidecar in each Container Apps replica"
  type        = bool
  default     = true
}

variable "datadog_sidecar_image" {
  description = "Immutable Datadog Agent image"
  type        = string
  default     = "docker.io/datadog/agent@sha256:c778490306882f4ed64ff61f5fe8d841ed9061ab52c19edf2afe0f3ba84ab650"
}

variable "datadog_sidecar_cpu" {
  description = "CPU cores allocated to the Datadog Agent sidecar"
  type        = number
  default     = 0.5

  validation {
    condition     = var.datadog_sidecar_cpu > 0
    error_message = "datadog_sidecar_cpu must be greater than zero."
  }
}

variable "datadog_sidecar_memory" {
  description = "Memory allocated to the Datadog Agent sidecar"
  type        = string
  default     = "1Gi"

  validation {
    condition     = can(regex("^[1-9][0-9]*(Mi|Gi)$", var.datadog_sidecar_memory))
    error_message = "datadog_sidecar_memory must use an Azure Container Apps value such as 1Gi."
  }
}

variable "min_replicas" {
  description = "Minimum number of Container Apps replicas"
  type        = number
  default     = 0

  validation {
    condition     = var.min_replicas >= 0
    error_message = "min_replicas cannot be negative."
  }
}

variable "max_replicas" {
  description = "Maximum number of Container Apps replicas"
  type        = number
  default     = 1

  validation {
    condition     = var.max_replicas >= 1
    error_message = "max_replicas must be at least one."
  }
}

variable "service_principal_name" {
  description = "Display name of the Service Principal for GitHub Actions"
  type        = string
  default     = "sp-github-rag-deploy"
}
