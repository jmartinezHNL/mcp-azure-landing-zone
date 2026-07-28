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
- Las funciones de `tools/resources.py` devuelven estructuras nativas de Python
  (`dict` / `list`); es `server.py` quien las serializa a JSON.

### Respuesta de error genérica

```json
{
  "status": "error",
  "message": "Permisos insuficientes: la identidad actual necesita al menos el rol 'Reader' sobre la subscripción.",
  "detail": "(AuthorizationFailed) The client '…' does not have authorization…"
}
```

`message` es un diagnóstico ya traducido (autenticación, 403, 404, conectividad);
`detail` conserva el mensaje original del SDK.

### Cuál usar en cada caso

| Pregunta del usuario | Herramienta |
|---|---|
| «¿Qué tengo desplegado?», «dame un mapa de la Landing Zone» | `get_subscription_topology` |
| «Dame el detalle / los ids de los recursos de `rg-x`» | `list_azure_resources` |
| «¿Qué recursos no están etiquetados?» | `list_untagged_resources` |
| «¿Cumplo mis políticas de seguridad?» | `get_policy_compliance` |
| «¿Coincide Terraform con la realidad?» | `detect_infrastructure_drift` |
| «¿Qué configuración estás usando?» | `get_server_configuration` |

---

## 3.1 `get_subscription_topology`

Topología jerarquizada por resource group, optimizada para consumir pocos tokens.
**Es la herramienta preferida para una visión de conjunto.**

### Parámetros

| Nombre | Tipo | Obligatorio | Por defecto | Descripción |
|---|---|---|---|---|
| `subscription_id` | string | No | `azure.default_subscription_id` | GUID de la subscripción |
| `include_resources` | bool | No | `true` | Si es `false`, cada grupo queda reducido a su recuento y su desglose por tipo |
| `max_resources_per_group` | int | No | `null` (sin tope) | Máximo de recursos detallados por grupo |

### Respuesta

```json
{
  "status": "ok",
  "subscription_id": "77308696-…",
  "summary": {
    "total_resource_groups": 42,
    "total_resources": 1634,
    "empty_resource_groups": 3,
    "resources_without_essential_tags": 1319,
    "locations": { "eastus": 1402, "canadacentral": 118 },
    "top_resource_types": {
      "Sql/servers/databases": 144,
      "Web/certificates": 142,
      "insights/components": 91
    },
    "distinct_resource_types": 68
  },
  "detail_level": "completo",
  "notes": "El campo 'type' omite el prefijo 'Microsoft.'. …",
  "resource_groups": {
    "rg-01": {
      "location": "eastus",
      "tags": { "environment": "prod" },
      "resource_count": 823,
      "types": { "Web/sites": 76, "Sql/servers/databases": 144 },
      "resources": [
        { "name": "plan-stage-01", "type": "Web/serverFarms",
          "tags": { "environment": "qa", "application": "meilisearchstage" } },
        { "name": "plan-stage-02", "type": "Web/serverFarms" }
      ]
    }
  }
}
```

| Campo | Significado |
|---|---|
| `summary.resources_without_essential_tags` | Recursos sin ninguna etiqueta de gobierno reconocida |
| `summary.top_resource_types` | Los 15 tipos más frecuentes (`TOP_RESOURCE_TYPES`) |
| `detail_level` | `"completo"` o `"solo-resumen"` según `include_resources` |
| `resource_groups` | Ordenado de **mayor a menor** número de recursos |
| `…[].types` | Desglose completo por tipo dentro del grupo |
| `…[].resources_truncated` | Presente y `true` si se aplicó `max_resources_per_group` |

### Optimizaciones de tokens

| Técnica | Efecto |
|---|---|
| `type` sin el prefijo `Microsoft.` | `Microsoft.Network/virtualNetworks` → `Network/virtualNetworks` |
| Campos vacíos omitidos | Un recurso sin tags no incluye la clave `tags` |
| `location` omitida si coincide con la del grupo | Elimina el campo en la mayoría de recursos |
| Tags filtradas a las de gobierno | `ESSENTIAL_TAG_KEYS`: `owner`, `costcenter`, `environment`, `project`… |
| Grupos ordenados por tamaño | Lo relevante entra primero en el contexto |

Medición real sobre una subscripción de 42 grupos y 1 634 recursos:

| Modo | Tamaño | Tokens aprox. |
|---|---|---|
| `include_resources=true` | 218 798 chars | ~54 700 |
| `max_resources_per_group=5` | 32 157 chars | ~8 000 |
| `include_resources=false` | **12 305 chars** | **~3 076** |

Los contadores de `summary` son idénticos en los tres modos: recortar el detalle
no altera las cifras.

> **Recomendación:** en subscripciones grandes, empieza siempre con
> `include_resources=false` y pide después el detalle del grupo concreto con
> `list_azure_resources`.

### Notas

- Los resource groups se leen antes que los recursos, de modo que los **grupos
  vacíos también aparecen** (con `resource_count: 0`).
- Los recursos cuyo id ARM no incluye resource group se agrupan bajo
  `(sin-resource-group)`.
- Una sola pasada paginada sobre `resources.list()`: no multiplica llamadas por grupo.

---

## 3.2 `list_azure_resources`

Vista plana y detallada, con el **id ARM completo**. Úsala cuando haga falta
identificar recursos de forma inequívoca o trabajar sobre un solo grupo.

### Parámetros

| Nombre | Tipo | Obligatorio | Por defecto | Descripción |
|---|---|---|---|---|
| `subscription_id` | string | No | `azure.default_subscription_id` | GUID de la subscripción |
| `resource_group` | string | No | `null` (toda la subscripción) | Nombre del resource group para acotar |

### Respuesta

```json
{
  "status": "ok",
  "subscription_id": "77308696-…",
  "resource_group": "rg-hnl-01",
  "count": 32,
  "resources": [
    {
      "name": "vnet-hub-prod",
      "type": "Network/virtualNetworks",
      "location": "eastus",
      "resource_group": "rg-hnl-01",
      "tags": { "source": "terraform", "stage": "production" },
      "id": "/subscriptions/7730…/providers/Microsoft.Network/virtualNetworks/vnet-hub-prod"
    }
  ]
}
```

| Campo | Significado |
|---|---|
| `count` | Número de recursos devueltos |
| `resources[].type` | Sin el prefijo `Microsoft.` (igual que en la topología) |
| `resources[].tags` | **Todas** las etiquetas, sin filtrar (a diferencia de la topología) |
| `resources[].id` | Id ARM completo, con el namespace del proveedor intacto |

### Notas

- Sin `resource_group` recorre toda la subscripción: en entornos grandes la
  respuesta puede ocupar decenas de miles de tokens. **Filtra siempre que puedas.**
- No incluye recursos a nivel de management group ni de tenant.

---

## 3.3 `list_untagged_resources`

Auditoría de gobierno: recursos sin **ninguna** etiqueta.

### Parámetros

| Nombre | Tipo | Obligatorio | Por defecto |
|---|---|---|---|
| `subscription_id` | string | No | `azure.default_subscription_id` |

### Respuesta

```json
{
  "status": "ok",
  "subscription_id": "77308696-…",
  "count": 1319,
  "untagged_resources": [
    {
      "name": "DefaultWorkspace-7730…-CCAN",
      "type": "OperationalInsights/workspaces",
      "location": "canadacentral",
      "resource_group": "DefaultResourceGroup-CCAN",
      "id": "/subscriptions/7730…/workspaces/DefaultWorkspace-7730…-CCAN"
    }
  ]
}
```

El resultado viene **ordenado por resource group y nombre**, lo que facilita
agrupar los hallazgos en el informe.

### Notas

- Criterio estricto: solo entra el recurso que **no tiene ninguna** etiqueta. Para
  «tiene tags pero le falta `costCenter`», usa una Azure Policy de tipo *Require a
  tag* y consulta `get_policy_compliance`.
- Para el **porcentaje** sobre el total, usa `get_subscription_topology`:
  `summary.resources_without_essential_tags` frente a `summary.total_resources`.
- Las etiquetas heredadas del resource group **no** cuentan: ARM solo devuelve las
  materializadas en el recurso.

---

## 3.4 `get_policy_compliance`

Estado de cumplimiento de Azure Policy (Policy Insights, snapshot `latest`).

### Parámetros

| Nombre | Tipo | Obligatorio | Por defecto |
|---|---|---|---|
| `subscription_id` | string | No | `azure.default_subscription_id` |

### Respuesta

```json
{
  "status": "ok",
  "subscription_id": "77308696-…",
  "total_evaluations": 512,
  "compliance_rate_percent": 87.5,
  "summary": { "Compliant": 448, "NonCompliant": 61, "Unknown": 3 },
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
| `by_policy_assignment` | Recuento por estado desglosado por asignación de política |
| `non_compliant_truncated` | `true` si había más de 100 incumplimientos y la lista se recortó |
| `non_compliant_resources` | Detalle, **limitado a los primeros 100 registros** |

### Notas

- A diferencia de las herramientas de recursos, aquí `resource_type` conserva el
  prefijo `Microsoft.` tal y como lo devuelve Policy Insights.
- Un mismo recurso aparece **una vez por cada política** que lo evalúa: por eso
  `total_evaluations` suele superar con creces el número de recursos.
- Los datos son del último ciclo de evaluación (~24 h). No es tiempo real.
- El límite de detalle está en `MAX_DETAIL_RECORDS` (`tools/policy.py`); el
  recuento total nunca se trunca.

---

## 3.5 `detect_infrastructure_drift`

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
| `1` | `ERROR` | Fallo de Terraform: falta `init`, credenciales del backend, sintaxis… |

### Notas de seguridad y límites

- **Solo lectura**: nunca ejecuta `apply` ni `destroy`.
- Se lanza con `shell=False` y lista de argumentos explícita → sin inyección de comandos.
- `working_dir` y `var_file` se normalizan a ruta absoluta y se valida su existencia.
- La salida se recorta a los **últimos 20 000 caracteres** (`MAX_OUTPUT_CHARS`),
  conservando el resumen final del plan.
- El timeout se toma de `terraform.timeout_seconds`; al agotarse, el proceso se aborta.
- `terraform plan` hace *refresh* contra Azure: puede tardar minutos.

---

## 3.6 `get_server_configuration`

Diagnóstico: muestra la configuración efectiva del servidor.

### Parámetros

Ninguno.

### Respuesta

```json
{
  "status": "ok",
  "config_path": "/Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/config.yaml",
  "config_exists": true,
  "azure": { "default_subscription_id": "77308696-…" },
  "terraform": {
    "working_dir": "/Users/juancarlosmartinez/infra/landing-zone/prod",
    "timeout_seconds": 600
  }
}
```

Úsala como primer paso cuando algo falle: confirma qué fichero se cargó y qué
valores están activos tras aplicar las variables de entorno.
