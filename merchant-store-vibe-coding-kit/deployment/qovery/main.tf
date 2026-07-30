locals {
  resource_prefix = substr(replace(lower(var.project_name), "_", "-"), 0, 30)
  public_base_url = "https://${var.store_domain}"
  kit_root_path   = trimsuffix(var.kit_repository_root_path, "/")
}

resource "qovery_project" "merchant_store" {
  organization_id = var.qovery_organization_id
  name            = var.project_name
  description     = "Ping Business merchant-hosted store"
}

resource "qovery_environment" "merchant_store" {
  project_id = qovery_project.merchant_store.id
  cluster_id = var.qovery_cluster_id
  name       = var.environment_name
  mode       = "PRODUCTION"

  depends_on = [qovery_project.merchant_store]
}

resource "qovery_deployment_stage" "database" {
  environment_id = qovery_environment.merchant_store.id
  name           = "01-database"
  description    = "Provision PostgreSQL first"
}

resource "qovery_deployment_stage" "identity" {
  environment_id = qovery_environment.merchant_store.id
  name           = "02-identity"
  description    = "Start Keycloak after PostgreSQL"
  is_after       = qovery_deployment_stage.database.id
}

resource "qovery_deployment_stage" "bootstrap" {
  environment_id = qovery_environment.merchant_store.id
  name           = "03-realm-bootstrap"
  description    = "Reconcile and verify the ESTORE realm before the backend"
  is_after       = qovery_deployment_stage.identity.id
}

resource "qovery_deployment_stage" "backend" {
  environment_id = qovery_environment.merchant_store.id
  name           = "04-backend"
  description    = "Deploy estore-app after identity verification"
  is_after       = qovery_deployment_stage.bootstrap.id
}

resource "qovery_deployment_stage" "frontend" {
  environment_id = qovery_environment.merchant_store.id
  name           = "05-frontend"
  description    = "Deploy the runtime-configured merchant UI"
  is_after       = qovery_deployment_stage.backend.id
}

resource "qovery_deployment_stage" "edge" {
  environment_id = qovery_environment.merchant_store.id
  name           = "06-edge"
  description    = "Expose only the edge router and merchant hostname"
  is_after       = qovery_deployment_stage.frontend.id
}

resource "qovery_database" "keycloak" {
  environment_id      = qovery_environment.merchant_store.id
  deployment_stage_id = qovery_deployment_stage.database.id
  name                = "${local.resource_prefix}-keycloak-db"
  type                = "POSTGRESQL"
  version             = var.database_version
  mode                = var.database_mode
  accessibility       = "PRIVATE"
  storage             = var.database_storage_gb
  instance_type       = var.database_mode == "MANAGED" ? var.database_instance_type : null
  cpu                 = var.database_mode == "CONTAINER" ? var.database_cpu_millicores : null
  memory              = var.database_mode == "CONTAINER" ? var.database_memory_mb : null

  lifecycle {
    precondition {
      condition     = var.database_mode != "MANAGED" || length(trimspace(var.database_instance_type)) > 0
      error_message = "database_instance_type is required when database_mode is MANAGED."
    }
  }

  depends_on = [qovery_deployment_stage.database]
}

resource "qovery_application" "keycloak" {
  environment_id      = qovery_environment.merchant_store.id
  deployment_stage_id = qovery_deployment_stage.identity.id
  name                = "${local.resource_prefix}-keycloak"

  git_repository = {
    url       = var.kit_repository_url
    branch    = var.kit_repository_branch
    root_path = "${local.kit_root_path}/keycloak"
  }

  build_mode      = "DOCKER"
  dockerfile_path = "Dockerfile"
  auto_deploy     = false
  cpu             = 1000
  memory          = 2048
  min_running_instances = 1
  max_running_instances = 1

  ports = [
    {
      name                = "http"
      internal_port       = 8080
      publicly_accessible = false
      protocol            = "HTTP"
    },
    {
      name                = "management"
      internal_port       = 9000
      publicly_accessible = false
      protocol            = "HTTP"
    }
  ]

  environment_variables = [
    { key = "KC_DB", value = "postgres" },
    { key = "KC_DB_URL", value = "jdbc:postgresql://${qovery_database.keycloak.internal_host}:${qovery_database.keycloak.port}/${qovery_database.keycloak.name}" },
    { key = "KC_DB_USERNAME", value = qovery_database.keycloak.login },
    { key = "KC_HTTP_ENABLED", value = "true" },
    { key = "KC_HOSTNAME", value = "${local.public_base_url}/auth" },
    { key = "KC_HOSTNAME_BACKCHANNEL_DYNAMIC", value = "true" },
    { key = "KC_PROXY_HEADERS", value = "xforwarded" },
    { key = "KC_HEALTH_ENABLED", value = "true" },
    { key = "KC_METRICS_ENABLED", value = "true" },
    { key = "KC_CACHE", value = "local" },
    { key = "ESTORE_REALM", value = var.estore_realm },
    { key = "ESTORE_CLIENT_ID", value = var.estore_client_id }
  ]

  secrets = [
    { key = "KC_DB_PASSWORD", value = qovery_database.keycloak.password },
    { key = "KC_BOOTSTRAP_ADMIN_USERNAME", value = var.keycloak_admin_username },
    { key = "KC_BOOTSTRAP_ADMIN_PASSWORD", value = var.keycloak_admin_password },
    { key = "ESTORE_CLIENT_SECRET", value = var.estore_client_secret }
  ]

  healthchecks = {
    readiness_probe = {
      type = {
        http = {
          port   = 9000
          path   = "/health/ready"
          scheme = "HTTP"
        }
      }
      initial_delay_seconds = 45
      period_seconds        = 10
      timeout_seconds       = 5
      success_threshold     = 1
      failure_threshold     = 18
    }
    liveness_probe = {
      type = {
        http = {
          port   = 9000
          path   = "/health/live"
          scheme = "HTTP"
        }
      }
      initial_delay_seconds = 90
      period_seconds        = 20
      timeout_seconds       = 5
      success_threshold     = 1
      failure_threshold     = 6
    }
  }

  depends_on = [qovery_database.keycloak]
}

resource "qovery_job" "realm_bootstrap" {
  environment_id      = qovery_environment.merchant_store.id
  deployment_stage_id = qovery_deployment_stage.bootstrap.id
  name                = "${local.resource_prefix}-realm-bootstrap"
  cpu                 = 250
  memory              = 256
  max_duration_seconds = 900
  max_nb_restart       = 2
  auto_deploy          = false

  schedule = {
    on_start = {
      entrypoint = "/usr/local/bin/python"
      arguments  = ["/app/bootstrap_realm.py"]
    }
  }

  source = {
    docker = {
      dockerfile_path = "realm-bootstrap/Dockerfile"
      git_repository = {
        url       = var.kit_repository_url
        branch    = var.kit_repository_branch
        root_path = "${local.kit_root_path}/keycloak"
      }
    }
  }

  healthchecks = {}

  environment_variables = [
    { key = "KC_SERVER_URL", value = "http://${qovery_application.keycloak.internal_host}:8080" },
    { key = "ESTORE_REALM", value = var.estore_realm },
    { key = "ESTORE_CLIENT_ID", value = var.estore_client_id },
    { key = "BOOTSTRAP_TIMEOUT_SECONDS", value = "600" },
    { key = "VERIFY_TIMEOUT_SECONDS", value = "300" }
  ]

  secrets = [
    { key = "KC_BOOTSTRAP_ADMIN_USERNAME", value = var.keycloak_admin_username },
    { key = "KC_BOOTSTRAP_ADMIN_PASSWORD", value = var.keycloak_admin_password },
    { key = "ESTORE_CLIENT_SECRET", value = var.estore_client_secret }
  ]

  depends_on = [qovery_application.keycloak]
}

resource "qovery_application" "estore_app" {
  environment_id      = qovery_environment.merchant_store.id
  deployment_stage_id = qovery_deployment_stage.backend.id
  name                = "${local.resource_prefix}-estore-app"

  git_repository = {
    url       = var.kit_repository_url
    branch    = var.kit_repository_branch
    root_path = "${local.kit_root_path}/source/estore-app"
  }

  build_mode      = "DOCKER"
  dockerfile_path = "Dockerfile"
  auto_deploy     = false
  cpu             = 500
  memory          = 1024
  min_running_instances = 1
  max_running_instances = 2

  ports = [
    {
      name                = "http"
      internal_port       = 5000
      publicly_accessible = false
      protocol            = "HTTP"
    }
  ]

  environment_variables = [
    { key = "DEV_MODE", value = "false" },
    { key = "ESTORE_APP_PORT", value = "5000" },
    { key = "BIZ_APP_BASE_URL", value = var.biz_app_base_url },
    { key = "ESTORE_PUBLIC_BASE_URL", value = "${local.public_base_url}/api" },
    { key = "ESTORE_KC_SERVER_URL", value = "http://${qovery_application.keycloak.internal_host}:8080" },
    { key = "ESTORE_REALM", value = var.estore_realm },
    { key = "ESTORE_CLIENT_ID", value = var.estore_client_id },
    { key = "ESTORE_ALLOWED_ORIGINS", value = local.public_base_url },
    { key = "ESTORE_TRUST_PROXY_HEADERS", value = "true" },
    { key = "ESTORE_CHECKOUT_FRAME_ANCESTORS", value = "'self'" },
    { key = "GUNICORN_WORKERS", value = "2" },
    { key = "GUNICORN_THREADS", value = "4" },
    { key = "GUNICORN_TIMEOUT", value = "120" }
  ]

  secrets = [
    { key = "PINGBIZ_MERCHANT_IDENTIFIER", value = var.pingbiz_merchant_identifier },
    { key = "PINGBIZ_STORE_IDENTIFIER", value = var.pingbiz_store_identifier },
    { key = "PINGBIZ_MERCHANT_API_KEY", value = var.pingbiz_merchant_api_key },
    { key = "ESTORE_CLIENT_SECRET", value = var.estore_client_secret }
  ]

  healthchecks = {
    readiness_probe = {
      type = {
        http = {
          port   = 5000
          path   = "/health"
          scheme = "HTTP"
        }
      }
      initial_delay_seconds = 20
      period_seconds        = 10
      timeout_seconds       = 5
      success_threshold     = 1
      failure_threshold     = 12
    }
    liveness_probe = {
      type = {
        http = {
          port   = 5000
          path   = "/health"
          scheme = "HTTP"
        }
      }
      initial_delay_seconds = 60
      period_seconds        = 20
      timeout_seconds       = 5
      success_threshold     = 1
      failure_threshold     = 6
    }
  }

  depends_on = [qovery_job.realm_bootstrap]
}

resource "qovery_application" "merchant_store" {
  environment_id      = qovery_environment.merchant_store.id
  deployment_stage_id = qovery_deployment_stage.frontend.id
  name                = "${local.resource_prefix}-merchant-store"

  git_repository = {
    url          = var.ui_repository_url
    branch       = var.ui_repository_branch
    root_path    = var.ui_repository_root_path
    git_token_id = length(trimspace(var.ui_git_token_id)) > 0 ? var.ui_git_token_id : null
  }

  build_mode      = "DOCKER"
  dockerfile_path = var.ui_dockerfile_path
  auto_deploy     = false
  cpu             = 250
  memory          = 256
  min_running_instances = 1
  max_running_instances = 2

  ports = [
    {
      name                = "http"
      internal_port       = 80
      publicly_accessible = false
      protocol            = "HTTP"
    }
  ]

  environment_variables = [
    { key = "ESTORE_APP_PUBLIC_URL", value = "/api" }
  ]

  healthchecks = {
    readiness_probe = {
      type = {
        http = {
          port   = 80
          path   = "/healthz"
          scheme = "HTTP"
        }
      }
      initial_delay_seconds = 10
      period_seconds        = 10
      timeout_seconds       = 5
      success_threshold     = 1
      failure_threshold     = 6
    }
  }

  depends_on = [qovery_application.estore_app]
}

resource "qovery_application" "edge" {
  environment_id      = qovery_environment.merchant_store.id
  deployment_stage_id = qovery_deployment_stage.edge.id
  name                = "${local.resource_prefix}-edge"

  git_repository = {
    url       = var.kit_repository_url
    branch    = var.kit_repository_branch
    root_path = "${local.kit_root_path}/deployment/edge"
  }

  build_mode      = "DOCKER"
  dockerfile_path = "Dockerfile"
  auto_deploy     = false
  cpu             = 250
  memory          = 256
  min_running_instances = 1
  max_running_instances = 2

  ports = [
    {
      name                = "https"
      internal_port       = 8080
      external_port       = 443
      publicly_accessible = true
      protocol            = "HTTP"
      is_default          = true
    }
  ]

  custom_domains = [
    {
      domain               = var.store_domain
      generate_certificate = true
      use_cdn              = var.use_cdn
    }
  ]

  environment_variables = [
    { key = "PUBLIC_HOST", value = var.store_domain },
    { key = "PUBLIC_SCHEME", value = "https" },
    { key = "PUBLIC_PORT", value = "443" },
    { key = "ESTORE_APP_UPSTREAM", value = "${qovery_application.estore_app.internal_host}:5000" },
    { key = "KEYCLOAK_UPSTREAM", value = "${qovery_application.keycloak.internal_host}:8080" },
    { key = "MERCHANT_STORE_UPSTREAM", value = "${qovery_application.merchant_store.internal_host}:80" }
  ]

  healthchecks = {
    readiness_probe = {
      type = {
        http = {
          port   = 8080
          path   = "/edge-health"
          scheme = "HTTP"
        }
      }
      initial_delay_seconds = 10
      period_seconds        = 10
      timeout_seconds       = 5
      success_threshold     = 1
      failure_threshold     = 6
    }
    liveness_probe = {
      type = {
        http = {
          port   = 8080
          path   = "/edge-health"
          scheme = "HTTP"
        }
      }
      initial_delay_seconds = 30
      period_seconds        = 20
      timeout_seconds       = 5
      success_threshold     = 1
      failure_threshold     = 6
    }
  }

  depends_on = [
    qovery_application.keycloak,
    qovery_application.estore_app,
    qovery_application.merchant_store
  ]
}

resource "qovery_deployment" "merchant_store" {
  environment_id = qovery_environment.merchant_store.id
  desired_state  = "RUNNING"

  depends_on = [
    qovery_database.keycloak,
    qovery_application.keycloak,
    qovery_job.realm_bootstrap,
    qovery_application.estore_app,
    qovery_application.merchant_store,
    qovery_application.edge
  ]
}
