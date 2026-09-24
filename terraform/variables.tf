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
  description = "CPU cores allocated to the application container (0.5 vCPU triples the free-grant runtime vs 1.5 vCPU with the old sidecar)"
  type        = number
  default     = 0.5

  validation {
    condition     = var.container_cpu > 0
    error_message = "container_cpu must be greater than zero."
  }
}

variable "container_memory" {
  description = "Memory allocated to the application container (the ONNX int8 service needs ~0.6 GiB)"
  type        = string
  default     = "1Gi"

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
  description = "Azure AI Search index for the v4 embedding space"
  type        = string
  default     = "ragdocs-v4"
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

variable "embedding_variant" {
  description = "Embedding runtime variant baked into the image and recorded on every indexed chunk"
  type        = string
  default     = "onnx-qint8"

  validation {
    condition     = contains(["onnx-qint8", "onnx-fp32"], var.embedding_variant)
    error_message = "embedding_variant must be onnx-qint8 or onnx-fp32."
  }
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
  description = "Run the Datadog Agent sidecar and enable APM tracing (adds 0.5 vCPU / 1 GiB per replica, a third of the free grant)"
  type        = bool
  default     = false
}

variable "datadog_sidecar_image" {
  description = "Immutable Datadog Agent image"
  type        = string
  default     = "docker.io/datadog/agent@sha256:29baa94e0a1abcadf43b2b2a002ad4406b3c05a46b8cae29ae1803a663795b59"
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
  description = "Maximum number of Container Apps replicas (the in-process query budget is per replica)"
  type        = number
  default     = 1

  validation {
    condition     = var.max_replicas >= 1
    error_message = "max_replicas must be at least one."
  }
}

variable "cooldown_period_seconds" {
  description = "Idle seconds before scaling back to zero; every cold visit bills at least this long"
  type        = number
  default     = 300

  validation {
    condition     = var.cooldown_period_seconds >= 60
    error_message = "cooldown_period_seconds must be at least 60."
  }
}

variable "max_inactive_revisions" {
  description = "Inactive revisions kept as rollback targets"
  type        = number
  default     = 5
}

variable "log_analytics_workspace_name" {
  description = "Existing workspace name to adopt (az containerapp env create generates workspace-<rg><suffix>); null creates log-<env>"
  type        = string
  default     = null
}

variable "log_analytics_daily_quota_gb" {
  description = "Daily Log Analytics ingestion cap; 0.16 GB/day stays inside the 5 GB/month free allowance"
  type        = number
  default     = 0.16

  validation {
    condition     = var.log_analytics_daily_quota_gb > 0
    error_message = "log_analytics_daily_quota_gb must be greater than zero."
  }
}

variable "service_principal_name" {
  description = "Display name of the Service Principal for GitHub Actions"
  type        = string
  default     = "sp-github-rag-deploy"
}
