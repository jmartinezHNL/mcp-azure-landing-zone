provider "azurerm" {
  subscription_id = var.subscription_id

  # El registro de resource providers requiere permisos de escritura sobre la
  # subscripción. Como esta configuración es de solo lectura, se desactiva para
  # que 'terraform plan' funcione con el rol Reader.
  resource_provider_registrations = "none"

  features {}
}
