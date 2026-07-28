output "subscription_id" {
  description = "Subscripción sobre la que se ha ejecutado el plan."
  value       = data.azurerm_subscription.current.subscription_id
}

output "subscription_display_name" {
  description = "Nombre legible de la subscripción."
  value       = data.azurerm_subscription.current.display_name
}

output "tenant_id" {
  description = "Tenant de Entra ID asociado a las credenciales actuales."
  value       = data.azurerm_client_config.current.tenant_id
}

output "effective_tags" {
  description = "Etiquetas que se aplicarán a los recursos gestionados."
  value       = local.tags
}
