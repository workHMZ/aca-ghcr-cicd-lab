# Resource Group
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
}

# Log Analytics Workspace (required by Container Apps Environment)
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${var.container_app_env_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

# Container Apps Environment
resource "azurerm_container_app_environment" "main" {
  name                       = var.container_app_env_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

# Container App (application image is updated by the CD pipeline)
resource "azurerm_container_app" "main" {
  name                         = var.container_app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Multiple"

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = var.container_app_name
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld@sha256:e9b3e7c34664c7cffd7144864b0e4eec369bfde80068f9095dc63b37058bec48"
      cpu    = var.container_cpu
      memory = var.container_memory

      env {
        name  = "AZURE_SEARCH_ENDPOINT"
        value = var.azure_search_endpoint
      }

      env {
        name  = "AZURE_SEARCH_INDEX_NAME"
        value = var.azure_search_index_name
      }

      env {
        name        = "AZURE_SEARCH_API_KEY"
        secret_name = "azure-search-api-key"
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-key"
      }

      env {
        name  = "OPENAI_MODEL"
        value = var.openai_model
      }

      env {
        name  = "OPENAI_REASONING_EFFORT"
        value = var.openai_reasoning_effort
      }

      env {
        name  = "EMBEDDING_MODEL"
        value = var.embedding_model
      }

      env {
        name  = "EMBEDDING_MODEL_REVISION"
        value = var.embedding_model_revision
      }

      env {
        name  = "EMBEDDING_OFFLINE"
        value = "1"
      }

      env {
        name  = "ENV_NAME"
        value = var.environment_name
      }

      env {
        name        = "DD_API_KEY"
        secret_name = "dd-api-key"
      }

      env {
        name  = "DD_SITE"
        value = var.datadog_site
      }

      env {
        name  = "DD_ENV"
        value = var.datadog_environment
      }

      env {
        name  = "DD_SERVICE"
        value = var.datadog_service
      }

      env {
        name  = "DD_TRACE_AGENT_URL"
        value = "http://127.0.0.1:8126"
      }

      startup_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        initial_delay           = 1
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 10
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/ready"
        interval_seconds        = 5
        timeout                 = 3
        failure_count_threshold = 6
        success_count_threshold = 1
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        initial_delay           = 60
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
  # image and registry credential updates. Secret values are created out of
  # band and intentionally never enter source control or Terraform state;
  # Terraform still documents and manages their application env references.
  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
      registry,
      secret,
    ]
  }
}
