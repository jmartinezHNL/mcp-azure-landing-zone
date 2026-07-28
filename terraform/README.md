# Configuración Terraform de la Landing Zone

Directorio sobre el que la herramienta MCP `detect_infrastructure_drift` ejecuta
`terraform plan` para comparar el código con la infraestructura real de Azure.

## Estado inicial

La configuración **no declara ningún recurso**: solo lee la subscripción y las
credenciales activas mediante *data sources* y expone algunos outputs. Por eso
`terraform plan` devuelve `No changes` (código de salida 0) y el servidor MCP
informa de **SIN DRIFT**.

Esa es la línea base. A medida que incorpores recursos, cada desviación entre el
código y la realidad se detectará automáticamente.

## Ficheros

| Fichero | Contenido |
|---|---|
| `versions.tf` | Versión mínima de Terraform, provider `azurerm ~> 4.0` y backend (local por defecto) |
| `providers.tf` | Configuración del provider `azurerm` |
| `variables.tf` | `subscription_id`, `location`, `environment`, `common_tags` |
| `main.tf` | Data sources, locals y ejemplo comentado de importación |
| `outputs.tf` | Subscripción, tenant y etiquetas efectivas |
| `terraform.tfvars` | Valores reales (**ignorado por git**) |
| `terraform.tfvars.example` | Plantilla versionable |
| `.terraform.lock.hcl` | Fijación de versiones del provider (**sí se versiona**) |

## Uso

```bash
cd terraform

terraform init      # ya ejecutado; repítelo si cambias providers o backend
terraform validate
terraform plan      # equivalente a lo que hace la herramienta MCP
```

Desde el asistente:

> ¿Hay drift entre mi código Terraform y la infraestructura real?

## Incorporar infraestructura existente

1. Declara el recurso tal y como existe hoy en Azure.
2. Añade un bloque `import` apuntando a su id ARM (ver ejemplo comentado en
   `main.tf`). Puedes obtener el id con la herramienta MCP
   `list_azure_resources`.
3. Ejecuta `terraform plan`: las diferencias que aparezcan son drift real
   (cambios hechos a mano desde el portal, tags añadidas fuera de Terraform...).
4. Cuando el plan salga limpio, elimina el bloque `import`.

## Notas

- El provider está configurado con `resource_provider_registrations = "none"`:
  registrar resource providers exige permisos de escritura y esta configuración
  está pensada para funcionar con el rol **Reader**.
- El state se guarda en local (`terraform.tfstate`, ignorado por git). Para
  trabajo en equipo, descomenta el bloque `backend "azurerm"` de `versions.tf`
  y vuelve a ejecutar `terraform init`.
- Las credenciales las resuelve el provider por la misma vía que el servidor MCP:
  la sesión de `az login` o las variables `ARM_*` / `AZURE_*`.
