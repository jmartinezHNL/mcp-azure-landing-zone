terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Backend local por defecto: el state queda en terraform.tfstate, ignorado
  # por git. Para trabajo en equipo, mueve el state a Azure Storage:
  #
  # backend "azurerm" {
  #   resource_group_name  = "rg-tfstate"
  #   storage_account_name = "sttfstatealz001"
  #   container_name       = "tfstate"
  #   key                  = "landing-zone.tfstate"
  # }
}
