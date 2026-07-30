output "project_id" {
  value = qovery_project.merchant_store.id
}

output "environment_id" {
  value = qovery_environment.merchant_store.id
}

output "storefront_url" {
  value = "https://${var.store_domain}"
}

output "estore_api_url" {
  value = "https://${var.store_domain}/api"
}

output "keycloak_url" {
  value = "https://${var.store_domain}/auth"
}

output "keycloak_admin_url" {
  value = "https://${var.store_domain}/auth/admin/"
}

output "dns_validation_target" {
  description = "Create a CNAME from store_domain to this Qovery validation domain, unless an authorized DNS agent does it automatically."
  value       = one(qovery_application.edge.custom_domains).validation_domain
}

output "qovery_temporary_edge_host" {
  description = "Qovery-generated edge hostname, useful while custom DNS is pending."
  value       = qovery_application.edge.external_host
}

output "keycloak_admin_username" {
  value = var.keycloak_admin_username
}

output "credential_retrieval" {
  value = "Retrieve generated credentials from the protected Terraform state or Qovery secret controls. Do not print secrets into chat or deployment logs."
}
