variable "subscription_id" {
  description = "GUID de la subscripción de Azure sobre la que opera la Landing Zone."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.subscription_id))
    error_message = "subscription_id debe ser un GUID de 36 caracteres."
  }
}

variable "location" {
  description = "Región de Azure por defecto para los recursos de la Landing Zone."
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Entorno lógico de esta configuración (prod, stage, dev...)."
  type        = string
  default     = "prod"
}

variable "common_tags" {
  description = "Etiquetas de gobierno aplicadas a todos los recursos gestionados."
  type        = map(string)
  default = {
    managedBy = "terraform"
    project   = "azure-landing-zone"
  }
}
