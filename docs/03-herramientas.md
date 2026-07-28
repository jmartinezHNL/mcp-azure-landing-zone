# 3. Referencia de herramientas

Convenciones comunes:

- Las herramientas de Azure devuelven **JSON serializado como texto**, siempre con
  un campo `status` (`"ok"` | `"error"`).
- `detect_infrastructure_drift` devuelve **texto plano estructurado** (es la salida
  de Terraform, que no es JSON).
- Ninguna herramienta lanza excepciones hacia el cliente MCP: los fallos se
  devuelven como contenido legible con `status: "error"` o un prefijo `ERROR:`.
- Los parámetros marcados como opcionales pueden omitirse; se rellenan desde
  `config.yaml`.

### Respuesta de error genérica

```json
{
  "status": "error",
  "message": "Error al consultar Azure Resource Manager.",
  "detail": "(SubscriptionNotFound) The subscription '0000…' could not be found."
}
```

---

## 3.1 `list_azure_resources`

Inventario de recursos desplegados.

### Parámetros

| Nombre | Tipo | Obligatorio | Por defecto | Descripción |
|---|---|---|---|---|
| `subscription_id` | string | No | `azure.default_subscription_id` | GUID de la subscripción |
| `resource_group` | string | No | `null` (toda la subscripción) | Nombre del resource group para acotar |

### Respuesta

```json
{
  "status": "ok",
  "subscription_id": "77308696-6250-4529-8d8d-66944e6f5f38",
  "resource_group": "rg-alz-hub-prod",
  "count": 2,
  "resources": [
    {
      "name": "vnet-hub-prod",
      "type": "Microsoft.Network/virtualNetworks",
      "location": "eastus",
      "resource_group": "rg-alz-hub-prod",
      "tags": { "env": "prod", "owner": "plataforma" },
      "id": "/subscriptions/7730.../resourceGroups/rg-alz-hub-prod/providers/Microsoft.Network/virtualNetworks/vnet-hub-prod"
    },
    {
      "name": "stalzlogsprod001",
      "type": "Microsoft.Storage/storageAccounts",
      "location": "eastus",
      "resource_group": "rg-alz-hub-prod",
      "tags": {},
      "id": "/subscriptions/7730.../resourceGroups/rg-alz-hub-prod/providers/Microsoft.Storage/storageAccounts/stalzlogsprod001"
    }
  ]
}
```

| Campo | Significado |
|---|---|
| `count` | Número de recursos devueltos |
| `resources[].resource_group` | Extraído del id ARM; `""` si el recurso no pertenece a ningún grupo |
| `resources[].tags` | Diccionario vacío `{}` si el recurso no tiene etiquetas |

### Notas

- Recorre **toda** la paginación de ARM: en subscripciones muy grandes la respuesta
  puede ser extensa. Filtra por `resource_group` siempre que puedas.
- No incluye recursos a nivel de management group ni de tenant.

---

## 3.2 `list_untagged_resources`

Auditoría de gobierno: recursos sin ninguna etiqueta.

### Parámetros

| Nombre | Tipo | Obligatorio | Por defecto |
|---|---|---|---|
| `subscription_id` | string | No | `azure.default_subscription_id` |

### Respuesta

```json
{
  "status": "ok",
  "subscription_id": "77308696-6250-4529-8d8d-66944e6f5f38",
  "total_resources": 142,
  "untagged_count": 17,
  "untagged_percentage": 11.97,
  "untagged_resources": [
    {
      "name": "stalzlogsprod001",
      "type": "Microsoft.Storage/storageAccounts",
      "location": "eastus",
      "resource_group": "rg-alz-hub-prod",
      "tags": {},
      "id": "/subscriptions/…"
    }
  ]
}
```

| Campo | Significado |
|---|---|
| `total_resources` | Recursos analizados en la subscripción |
| `untagged_count` | Cuántos no tienen ninguna etiqueta |
| `untagged_percentage` | Porcentaje sobre el total, redondeado a 2 decimales |

### Notas

- Un recurso se considera *sin etiquetar* solo si **no tiene ninguna** etiqueta.
  No detecta el caso «tiene tags pero le falta `costCenter`»; para eso usa una
  Azure Policy de tipo *Require a tag* y consulta `get_policy_compliance`.
- Las etiquetas heredadas del resource group **no** se reflejan aquí: ARM las
  devuelve solo si están materializadas en el recurso.

---

## 3.3 `get_policy_compliance`

Estado de cumplimiento de Azure Policy (Policy Insights, snapshot `latest`).

### Parámetros

| Nombre | Tipo | Obligatorio | Por defecto |
|---|---|---|---|
| `subscription_id` | string | No | `azure.default_subscription_id` |

### Respuesta

```json
{
  "status": "ok",
  "subscription_id": "77308696-6250-4529-8d8d-66944e6f5f38",
  "total_evaluations": 512,
  "compliance_rate_percent": 87.5,
  "summary": {
    "Compliant": 448,
    "NonCompliant": 61,
    "Unknown": 3
  },
  "by_policy_assignment": {
    "require-tag-costcenter": { "Compliant": 120, "NonCompliant": 22 },
    "deny-public-ip": { "Compliant": 98 }
  },
  "non_compliant_count": 61,
  "non_compliant_truncated": false,
  "non_compliant_resources": [
    {
      "resource_id": "/subscriptions/…/storageAccounts/stalzlogsprod001",
      "resource_type": "Microsoft.Storage/storageAccounts",
      "resource_group": "rg-alz-hub-prod",
      "compliance_state": "NonCompliant",
      "policy_definition_id": "/providers/Microsoft.Authorization/policyDefinitions/…",
      "policy_definition_action": "audit",
      "policy_assignment_name": "require-tag-costcenter",
      "policy_set_definition_name": null,
      "is_compliant": false
    }
  ]
}
```

| Campo | Significado |
|---|---|
| `total_evaluations` | Pares (recurso, política) evaluados, no número de recursos |
| `compliance_rate_percent` | `Compliant / total × 100` |
| `summary` | Recuento por estado de cumplimiento |
| `by_policy_assignment` | Mismo recuento desglosado por asignación de política |
| `non_compliant_truncated` | `true` si había más de 100 incumplimientos y la lista se recortó |
| `non_compliant_resources` | Detalle, **limitado a los primeros 100 registros** |

### Notas

- Un mismo recurso aparece **una vez por cada política** que lo evalúa: por eso
  `total_evaluations` suele ser mucho mayor que el número de recursos.
- Los datos provienen del último ciclo de evaluación de Azure Policy (se refresca
  cada ~24 h o tras un escaneo bajo demanda). No es tiempo real.
- El límite de 100 registros de detalle está en `MAX_DETAIL_RECORDS`
  (`tools/policy.py`); el recuento total nunca se trunca.

---

## 3.4 `detect_infrastructure_drift`

Ejecuta `terraform plan -no-color -input=false -detailed-exitcode` en local.

### Parámetros

| Nombre | Tipo | Obligatorio | Por defecto | Descripción |
|---|---|---|---|---|
| `working_dir` | string | No | `terraform.working_dir` | Directorio con la configuración Terraform |
| `var_file` | string | No | `null` | Ruta a un fichero `.tfvars` (`-var-file`) |

### Respuesta (texto plano)

```
Directorio: /Users/juancarlosmartinez/infra/landing-zone/prod

Comando: /opt/homebrew/bin/terraform plan -no-color -input=false -detailed-exitcode

Código de salida: 2

DRIFT DETECTADO: hay cambios pendientes entre el estado y el código.

--- SALIDA (stdout) ---
Terraform will perform the following actions:

  # azurerm_storage_account.logs will be updated in-place
  ~ resource "azurerm_storage_account" "logs" {
      ~ min_tls_version = "TLS1_0" -> "TLS1_2"
    }

Plan: 0 to add, 1 to change, 0 to destroy.
```

### Interpretación del código de salida

| Código | Veredicto | Significado |
|---|---|---|
| `0` | `SIN DRIFT` | El estado real coincide con el código |
| `2` | `DRIFT DETECTADO` | Hay cambios pendientes por aplicar |
| `1` | `ERROR` | Fallo de Terraform: falta `init`, credenciales del backend, sintaxis, etc. |

### Notas de seguridad y límites

- **Solo lectura**: nunca ejecuta `apply` ni `destroy`.
- Se lanza con `shell=False` y lista de argumentos explícita → sin inyección de comandos.
- `working_dir` y `var_file` se normalizan a ruta absoluta y se valida su existencia
  antes de ejecutar nada.
- La salida se recorta a los **últimos 20 000 caracteres** (`MAX_OUTPUT_CHARS`),
  conservando el resumen final del plan, que es la parte relevante.
- El timeout se toma de `terraform.timeout_seconds`; al agotarse, el proceso se aborta.
- `terraform plan` hace *refresh* del estado contra Azure: puede tardar minutos y
  consume llamadas a la API.

---

## 3.5 `get_server_configuration`

Diagnóstico: muestra la configuración efectiva del servidor.

### Parámetros

Ninguno.

### Respuesta

```json
{
  "status": "ok",
  "config_path": "/Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/config.yaml",
  "config_exists": true,
  "azure": { "default_subscription_id": "77308696-6250-4529-8d8d-66944e6f5f38" },
  "terraform": {
    "working_dir": "/Users/juancarlosmartinez/infra/landing-zone/prod",
    "timeout_seconds": 600
  }
}
```

Úsala como primer paso cuando algo no funcione: confirma qué fichero se cargó y
qué valores están activos tras aplicar las variables de entorno.
