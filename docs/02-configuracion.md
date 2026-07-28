# 2. Configuración — guía de llenado de información

Este documento explica **qué información hay que rellenar, de dónde sacarla y
qué formato debe tener**.

---

## 2.1 Fichero `config.yaml`

Ubicación por defecto: la raíz del proyecto, junto a `server.py`.
Se puede mover con la variable de entorno `MCP_ALZ_CONFIG` (ver §2.3).

```yaml
azure:
  default_subscription_id: "77308696-6250-4529-8d8d-66944e6f5f38"

terraform:
  working_dir: "/Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/terraform"
  timeout_seconds: 600
```

### Referencia de campos

| Campo | Tipo | Obligatorio | Valor por defecto | Descripción |
|---|---|---|---|---|
| `azure.default_subscription_id` | string (GUID) | Sí, salvo que pases `subscription_id` en cada llamada | `""` | Subscripción usada cuando la herramienta se invoca sin subscripción explícita |
| `terraform.working_dir` | string (ruta absoluta) | Solo para detección de drift | `""` | Directorio raíz de la configuración Terraform de la Landing Zone |
| `terraform.timeout_seconds` | entero (segundos) | No | `600` | Tiempo máximo de ejecución de `terraform plan` antes de abortar |

Si el fichero no existe, está corrupto o no es un mapa YAML válido, el servidor
**no falla**: registra un aviso en stderr y arranca con los valores por defecto
(vacíos). Compruébalo siempre con la herramienta `get_server_configuration`.

---

## 2.2 Cómo obtener cada valor

### `azure.default_subscription_id`

```bash
# Subscripción activa
az account show --query id -o tsv

# Todas las subscripciones a las que tienes acceso
az account list --query "[].{Nombre:name, Id:id, Estado:state}" -o table
```

Formato: GUID en minúsculas, entre comillas.
✅ `"77308696-6250-4529-8d8d-66944e6f5f38"`
❌ `"aludra Cloud"` (el nombre no sirve, debe ser el id)
❌ `/subscriptions/7730.../` (sin prefijo de ruta ARM)

### `terraform.working_dir`

Es el directorio donde **ejecutarías tú mismo** `terraform plan`, es decir el que
contiene los `.tf` del entorno **y** el `.terraform/` generado por `terraform init`.

```bash
# Desde el directorio de tu código Terraform:
pwd                      # copia esta ruta
ls -d .terraform         # debe existir; si no, ejecuta 'terraform init'
```

Requisitos del directorio:

1. Contiene los ficheros `.tf` del entorno.
2. Se ha ejecutado `terraform init` en él (existe `.terraform/`).
3. El backend del state (Azure Storage, Terraform Cloud, local…) es accesible con
   las credenciales del proceso que ejecuta el servidor MCP.
4. Si tu configuración necesita variables, prepara un `.tfvars` y pásalo con el
   parámetro `var_file` de la herramienta (ver
   [03-herramientas.md](03-herramientas.md#34-detect_infrastructure_drift)).

Formato: ruta **absoluta**, sin `~`.
✅ `"/Users/juancarlosmartinez/infra/landing-zone/prod"`
❌ `"~/infra/landing-zone/prod"` — el `~` sí se expande en el parámetro de la
herramienta, pero es mejor evitarlo en el fichero por claridad.
❌ `"./terraform"` — se resolvería contra el directorio de trabajo del cliente MCP,
que no es necesariamente el del proyecto.

### `terraform.timeout_seconds`

| Tamaño de la Landing Zone | Valor recomendado |
|---|---|
| < 50 recursos | 300 |
| 50 – 300 recursos | 600 (por defecto) |
| > 300 recursos o *refresh* lento | 900 – 1800 |

Ten en cuenta que muchos clientes MCP tienen su propio timeout de herramienta
(en torno a 60 s en algunas versiones de Claude Desktop). Si el plan es muy
largo, considera ejecutarlo con `-refresh=false` fuera del servidor o dividir la
configuración en módulos más pequeños.

---

## 2.3 Variables de entorno

Las variables de entorno **tienen prioridad sobre `config.yaml`**.

| Variable | Sustituye a | Ejemplo |
|---|---|---|
| `MCP_ALZ_CONFIG` | Ruta del fichero de configuración | `/etc/mcp/alz.yaml` |
| `AZURE_SUBSCRIPTION_ID` | `azure.default_subscription_id` | `77308696-…` |
| `TERRAFORM_WORKING_DIR` | `terraform.working_dir` | `/opt/infra/prod` |

Orden de resolución de la subscripción, de mayor a menor prioridad:

```
1. Parámetro subscription_id de la llamada a la herramienta
2. Variable de entorno AZURE_SUBSCRIPTION_ID
3. azure.default_subscription_id de config.yaml
4. (ninguno) -> la herramienta devuelve un error explicativo
```

> **Importante:** el servidor **no lee ficheros `.env` automáticamente** (no usa
> `python-dotenv`). El fichero `.env.example` es solo una plantilla. Para que las
> variables lleguen al proceso, expórtalas antes de arrancar:
>
> ```bash
> set -a; source .env; set +a
> .venv/bin/python server.py
> ```
>
> …o decláralas en el bloque `env` de la configuración de tu cliente MCP
> (ver [04-uso.md](04-uso.md)).

---

## 2.4 Métodos de autenticación

El servidor usa `DefaultAzureCredential`, que prueba estos mecanismos **en orden**
y se queda con el primero que funcione:

| Orden | Mecanismo | Cuándo aplica | Qué debes rellenar |
|---|---|---|---|
| 1 | Variables de entorno (service principal) | CI/CD, servidores | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` |
| 2 | Workload Identity | AKS con federación de identidad | Anotaciones del pod |
| 3 | Managed Identity | VM, App Service, Container Apps de Azure | Nada (asignar la identidad al recurso) |
| 4 | Azure CLI | Máquina de desarrollo | `az login` |
| 5 | Azure Developer CLI / PowerShell | Alternativas locales | `azd auth login` |

El navegador interactivo está **deshabilitado** a propósito
(`exclude_interactive_browser_credential=True`) para que un proceso stdio nunca
se quede colgado esperando un login manual.

### Opción A — Desarrollo local (recomendada aquí)

```bash
az login
az account set --subscription 77308696-6250-4529-8d8d-66944e6f5f38
```

Nada más que rellenar: el SDK reutiliza el token del CLI.

### Opción B — Service principal (desatendido)

```bash
# Crear el service principal con rol de solo lectura sobre la subscripción
az ad sp create-for-rbac \
  --name "mcp-azure-landing-zone" \
  --role "Reader" \
  --scopes "/subscriptions/<SUBSCRIPTION_ID>"
```

La salida contiene `appId`, `password` y `tenant`. Trasládalos a variables de entorno:

| Salida de `az` | Variable de entorno |
|---|---|
| `tenant` | `AZURE_TENANT_ID` |
| `appId` | `AZURE_CLIENT_ID` |
| `password` | `AZURE_CLIENT_SECRET` |

> El `password` se muestra **una sola vez**. Guárdalo en un gestor de secretos o
> en Azure Key Vault; nunca lo escribas en `config.yaml` ni lo subas a git.

---

## 2.5 Permisos necesarios en Azure

| Herramienta | Permiso mínimo | Rol integrado sugerido |
|---|---|---|
| `list_azure_resources` | `Microsoft.Resources/subscriptions/resources/read` | **Reader** |
| `list_untagged_resources` | igual que la anterior | **Reader** |
| `get_policy_compliance` | `Microsoft.PolicyInsights/policyStates/queryResults/action` | **Reader** suele bastar; si recibes `403 AuthorizationFailed`, asigna **Security Reader** o **Resource Policy Contributor** |
| `detect_infrastructure_drift` | Lectura sobre todos los recursos gestionados por el state + acceso al backend | **Reader** sobre el ámbito + permisos del backend (p. ej. *Storage Blob Data Reader* si el state está en Azure Storage) |

Asignación de rol a nivel de subscripción:

```bash
az role assignment create \
  --assignee "<appId-o-email-del-usuario>" \
  --role "Reader" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>"
```

Si tu Landing Zone tiene varias subscripciones bajo un management group, asigna
el rol a nivel de management group para cubrirlas todas:

```bash
az role assignment create \
  --assignee "<appId>" \
  --role "Reader" \
  --scope "/providers/Microsoft.Management/managementGroups/<MG_ID>"
```

---

## 2.6 Trabajar con varias subscripciones

`config.yaml` define **una sola** subscripción por defecto, pero todas las
herramientas aceptan `subscription_id` como parámetro. Con eso basta para
consultar cualquier otra sobre la marcha:

> «Lista los recursos de la subscripción `11111111-2222-3333-4444-555555555555`»

Si trabajas habitualmente con varios entornos, la opción más limpia es registrar
**varias instancias del servidor** en el cliente MCP, cada una con su fichero de
configuración:

```json
{
  "mcpServers": {
    "alz-prod": {
      "command": "/ruta/.venv/bin/python",
      "args": ["/ruta/server.py"],
      "env": { "MCP_ALZ_CONFIG": "/ruta/config.prod.yaml" }
    },
    "alz-dev": {
      "command": "/ruta/.venv/bin/python",
      "args": ["/ruta/server.py"],
      "env": { "MCP_ALZ_CONFIG": "/ruta/config.dev.yaml" }
    }
  }
}
```

---

## 2.7 Checklist de configuración

- [ ] `az login` ejecutado (o variables `AZURE_*` del service principal exportadas)
- [ ] Rol *Reader* asignado sobre la subscripción o el management group
- [ ] `azure.default_subscription_id` con el GUID real (no el placeholder `0000…`)
- [ ] `terraform.working_dir` apuntando a un directorio existente con `terraform init` hecho
- [ ] `terraform` disponible en el `PATH` del proceso del servidor
- [ ] `get_server_configuration` devuelve los valores esperados
- [ ] `list_azure_resources` devuelve `"status": "ok"`
