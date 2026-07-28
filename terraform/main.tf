# Configuración raíz de la Azure Landing Zone.
#
# Estado inicial: solo lectura. No declara ningún recurso, por lo que
# 'terraform plan' devuelve "No changes" (código de salida 0) y la herramienta
# MCP 'detect_infrastructure_drift' informa de "SIN DRIFT".
#
# A medida que incorpores recursos a Terraform, cada desviación entre el código
# y la infraestructura real pasará a detectarse automáticamente.

data "azurerm_subscription" "current" {}

data "azurerm_client_config" "current" {}

locals {
  # Etiquetas efectivas: las comunes más el entorno de esta configuración.
  tags = merge(var.common_tags, { environment = var.environment })
}

# ---------------------------------------------------------------------------
# Cómo empezar a gestionar infraestructura existente
# ---------------------------------------------------------------------------
# 1. Declara el recurso tal y como existe hoy en Azure:
#
# resource "azurerm_resource_group" "hub" {
#   name     = "rg-hnl-01"
#   location = var.location
#   tags     = local.tags
# }
#
# 2. Impórtalo al state sin recrearlo (Terraform >= 1.5, bloque declarativo):
#
# import {
#   to = azurerm_resource_group.hub
#   id = "/subscriptions/${var.subscription_id}/resourceGroups/rg-hnl-01"
# }
#
# 3. Ejecuta 'terraform plan'. Si el código no refleja el estado real (por
#    ejemplo, faltan tags aplicadas a mano desde el portal), el plan mostrará
#    esas diferencias: eso es exactamente el drift que detecta el servidor MCP.
#
# 4. Cuando el plan salga limpio, elimina el bloque 'import'.
