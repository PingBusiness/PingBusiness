variable "qovery_organization_id" {
  description = "Existing Qovery organization UUID discovered by the deployment agent."
  type        = string
}

variable "qovery_cluster_id" {
  description = "Existing deployed Qovery cluster UUID selected or provisioned by the deployment agent."
  type        = string
}

variable "project_name" {
  description = "Qovery project name for this merchant store."
  type        = string
}

variable "environment_name" {
  description = "Qovery environment name."
  type        = string
  default     = "production"
}

variable "kit_repository_url" {
  description = "Public Git repository containing this vibe kit."
  type        = string
  default     = "https://github.com/PingBusiness/PingBusiness"
}

variable "kit_repository_branch" {
  type    = string
  default = "main"
}

variable "kit_repository_root_path" {
  description = "Path from the repository root to the merchant-store vibe kit."
  type        = string
  default     = "/merchant-store-vibe-coding-kit"
  validation {
    condition     = startswith(var.kit_repository_root_path, "/")
    error_message = "kit_repository_root_path must start with /."
  }
}

variable "ui_repository_url" {
  description = "Public or authorized Git repository containing the selected merchant-store UI."
  type        = string
}

variable "ui_repository_branch" {
  type    = string
  default = "main"
}

variable "ui_repository_root_path" {
  type    = string
  default = "/merchant-store-vibe-coding-kit/source/merchant-store"
}

variable "ui_dockerfile_path" {
  description = "Dockerfile path relative to ui_repository_root_path."
  type        = string
  default     = "Dockerfile"
}

variable "ui_git_token_id" {
  description = "Optional Qovery Git token UUID for a private customized UI repository."
  type        = string
  default     = ""
}

variable "store_domain" {
  description = "Single public merchant-store hostname. /api and /auth are routed by the edge service."
  type        = string
}

variable "store_display_name" {
  description = "Optional non-secret metadata retained for deployment automation."
  type        = string
  default     = ""
}

variable "store_support_email" {
  description = "Optional non-secret metadata retained for deployment automation."
  type        = string
  default     = ""
}

variable "pingbusiness_environment" {
  description = "Merchant-facing Ping Business environment. scripts/prepare-deployment.py derives biz_app_base_url from this value."
  type        = string
  default     = "staging"
  validation {
    condition     = contains(["staging", "production"], var.pingbusiness_environment)
    error_message = "pingbusiness_environment must be staging or production."
  }
}

variable "biz_app_base_url" {
  description = "Derived by scripts/prepare-deployment.py. Do not expose as a merchant-facing free-form input."
  type        = string
}

variable "pingbiz_merchant_identifier" {
  type      = string
  sensitive = true
}

variable "pingbiz_store_identifier" {
  type      = string
  sensitive = true
}

variable "pingbiz_merchant_api_key" {
  type      = string
  sensitive = true
}

variable "estore_realm" {
  type    = string
  default = "ESTORE"
}

variable "estore_client_id" {
  type    = string
  default = "estore-app"
}

variable "estore_client_secret" {
  type      = string
  sensitive = true
}

variable "keycloak_admin_username" {
  type    = string
  default = "admin"
}

variable "keycloak_admin_password" {
  type      = string
  sensitive = true
}

variable "database_mode" {
  description = "Qovery PostgreSQL mode: MANAGED for production or CONTAINER for evaluation."
  type        = string
  default     = "MANAGED"

  validation {
    condition     = contains(["MANAGED", "CONTAINER"], var.database_mode)
    error_message = "database_mode must be MANAGED or CONTAINER."
  }
}

variable "database_version" {
  type    = string
  default = "16"
}

variable "database_storage_gb" {
  type    = number
  default = 20

  validation {
    condition     = var.database_storage_gb >= 10
    error_message = "database_storage_gb must be at least 10."
  }
}

variable "database_instance_type" {
  description = "Cloud-provider database instance type. Required when database_mode is MANAGED."
  type        = string
  default     = ""
}

variable "database_cpu_millicores" {
  description = "CPU used only when database_mode is CONTAINER."
  type        = number
  default     = 500
}

variable "database_memory_mb" {
  description = "Memory used only when database_mode is CONTAINER."
  type        = number
  default     = 1024
}

variable "use_cdn" {
  description = "Set true only when the store hostname is intentionally proxied through a CDN such as Cloudflare."
  type        = bool
  default     = false
}
