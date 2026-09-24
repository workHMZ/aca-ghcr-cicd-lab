# Resource Group
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
}

# Log Analytics Workspace (required by Container Apps Environment).
# The first 5 GB/month of ingestion is free; the daily cap guarantees an
# idle-by-default lab can never be billed for a log storm.
resource "azurerm_log_analytics_workspace" "main" {
  name                = coalesce(var.log_analytics_workspace_name, "log-${var.container_app_env_name}")
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = var.log_analytics_daily_quota_gb
}

# Container Apps Environment (Consumption: billed per active replica-second,
# with a monthly free grant of 180,000 vCPU-s and 360,000 GiB-s).
resource "azurerm_container_app_environment" "main" {
  name                       = var.container_app_env_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

locals {
  app_env = {
    AZURE_SEARCH_ENDPOINT    = var.azure_search_endpoint
    AZURE_SEARCH_INDEX_NAME  = var.azure_search_index_name
    OPENAI_MODEL             = var.openai_model
    OPENAI_REASONING_EFFORT  = var.openai_reasoning_effort
    EMBEDDING_MODEL          = var.embedding_model
    EMBEDDING_MODEL_REVISION = var.embedding_model_revision
    EMBEDDING_VARIANT        = var.embedding_variant
    EMBEDDING_OFFLINE        = "1"
    EMBEDDING_THREADS        = "1"
    ENV_NAME                 = var.environment_name
    DD_TRACE_ENABLED         = tostring(var.enable_datadog_sidecar)
  }
  datadog_env = {
    DD_SITE            = var.datadog_site
    DD_ENV             = var.datadog_environment
    DD_SERVICE         = var.datadog_service
    DD_TRACE_AGENT_URL = "http://127.0.0.1:8126"
  }
}

# Container App (application image is updated by the CD pipeline)
resource "azurerm_container_app" "main" {
  name                         = var.container_app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Multiple"
  # Inactive revisions cost nothing, but capping them keeps recent rollback
  # targets without accumulating dozens of stale revisions.
  max_inactive_revisions = var.max_inactive_revisions

  template {
    min_replicas               = var.min_replicas
    max_replicas               = var.max_replicas
    cooldown_period_in_seconds = var.cooldown_period_seconds

    http_scale_rule {
      name                = "http-scaler"
      concurrent_requests = "10"
    }

    container {
      name   = var.container_app_name
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld@sha256:e9b3e7c34664c7cffd7144864b0e4eec369bfde80068f9095dc63b37058bec48"
      cpu    = var.container_cpu
      memory = var.container_memory

      dynamic "env" {
        for_each = merge(local.app_env, var.enable_datadog_sidecar ? local.datadog_env : {})

        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name        = "AZURE_SEARCH_API_KEY"
        secret_name = "azure-search-api-key"
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-key"
      }

      dynamic "env" {
        for_each = var.enable_datadog_sidecar ? [1] : []

        content {
          name        = "DD_API_KEY"
          secret_name = "dd-api-key"
        }
      }

      # /health does not touch dependencies, so it gates startup as soon as
      # uvicorn listens; a 1 s interval avoids adding probe latency to every
      # scale-from-zero cold start.
      startup_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        initial_delay           = 0
        interval_seconds        = 1
        timeout                 = 2
        failure_count_threshold = 60
      }

      # /ready is a flag check once the model is loaded (no inference per probe).
      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/ready"
        interval_seconds        = 2
        timeout                 = 3
        failure_count_threshold = 10
        success_count_threshold = 1
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        initial_delay           = 30
        interval_seconds        = 30
        timeout                 = 5
        failure_count_threshold = 3
      }
    }

    dynamic "container" {
      for_each = var.enable_datadog_sidecar ? [1] : []

      content {
        name   = "datadog-agent"
        image  = var.datadog_sidecar_image
        cpu    = var.datadog_sidecar_cpu
        memory = var.datadog_sidecar_memory

        env {
          name        = "DD_API_KEY"
          secret_name = "dd-api-key"
        }

        env {
          name  = "DD_SITE"
          value = var.datadog_site
        }

        env {
          name  = "DD_APM_ENABLED"
          value = "true"
        }

        env {
          name  = "DD_APM_NON_LOCAL_TRAFFIC"
          value = "true"
        }

        env {
          name  = "DD_ENV"
          value = var.datadog_environment
        }

        env {
          name  = "DD_IGNORE_AUTOCONF"
          value = "kubelet"
        }

        env {
          name  = "DD_HOSTNAME"
          value = var.container_app_name
        }
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  # This resource reconciles the already-bootstrapped lab environment; it is
  # not a self-contained secret bootstrap. CD owns the immutable application
  # image, per-revision traffic, and registry credential updates. Secret values
  # are created out of band and intentionally never enter source control or
  # Terraform state; Terraform still documents and manages their env references.
  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
      ingress[0].traffic_weight,
      registry,
      secret,
    ]
  }
}
