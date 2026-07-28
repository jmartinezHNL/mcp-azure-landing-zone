# mcp-azure-landing-zone

Servidor **MCP (Model Context Protocol)** que permite a un asistente de IA (Claude Desktop,
Claude Code, o cualquier cliente MCP) inspeccionar y auditar una **Azure Landing Zone**:

- Inventariar los recursos desplegados en una subscripción.
- Auditar el gobierno de etiquetado (recursos sin *tags*).
- Evaluar el cumplimiento de **Azure Policy** vía Policy Insights.
- Detectar **drift de infraestructura** ejecutando `terraform plan` en local.

Todas las operaciones son **de solo lectura**: el servidor nunca crea, modifica ni elimina
recursos, y nunca ejecuta `terraform apply`.

---

## Índice de documentación

| Documento | Contenido |
|---|---|
| [docs/01-instalacion.md](docs/01-instalacion.md) | Requisitos, instalación paso a paso, verificación |
| [docs/02-configuracion.md](docs/02-configuracion.md) | **Llenado de `config.yaml`**, variables de entorno, autenticación y permisos de Azure |
| [docs/03-herramientas.md](docs/03-herramientas.md) | Referencia de cada herramienta: parámetros, salida, ejemplos |
| [docs/04-uso.md](docs/04-uso.md) | Registro en Claude Desktop / Claude Code y prompts de ejemplo |
| [docs/05-troubleshooting.md](docs/05-troubleshooting.md) | Errores frecuentes y su solución |

---

## Arquitectura

```
┌──────────────────┐   stdio (JSON-RPC)   ┌─────────────────────────────┐
│  Claude Desktop  │ ───────────────────► │  server.py  (FastMCP)       │
│  / Claude Code   │ ◄─────────────────── │  "Azure Landing Zone Asst."  │
└──────────────────┘                      └──────────┬──────────────────┘
                                                     │
                        ┌────────────────────────────┼────────────────────────────┐
                        ▼                            ▼                            ▼
              ┌───────────────────┐      ┌────────────────────┐      ┌────────────────────┐
              │ tools/resources.py│      │  tools/policy.py   │      │ tools/terraform.py │
              │ ResourceMgmtClient│      │ PolicyInsightsClient│     │ subprocess: plan   │
              └─────────┬─────────┘      └──────────┬─────────┘      └─────────┬──────────┘
                        │  DefaultAzureCredential   │                          │
                        ▼                            ▼                          ▼
                 ┌──────────────────────────────────────┐        ┌──────────────────────┐
                 │     Azure Resource Manager (ARM)     │        │  Terraform + state   │
                 └──────────────────────────────────────┘        └──────────────────────┘
```

### Estructura de ficheros

```
mcp-azure-landing-zone/
├── server.py                 # Punto de entrada MCP (FastMCP, transporte stdio)
├── config.yaml               # Configuración activa (NO subir a git si lleva datos reales)
├── config.example.yaml       # Plantilla de configuración
├── requirements.txt          # Dependencias
├── .env.example              # Plantilla de variables de entorno
├── terraform/                # Configuración Terraform de la Landing Zone
│   ├── versions.tf           # Versiones y backend
│   ├── providers.tf          # Provider azurerm
│   ├── variables.tf          # Variables de entrada
│   ├── main.tf               # Data sources y ejemplo de importación
│   └── outputs.tf            # Outputs de la configuración
├── tools/
│   ├── __init__.py
│   ├── resources.py          # get_full_subscription_topology / get_untagged_resources / list_resources
│   ├── policy.py             # get_policy_states
│   └── terraform.py          # run_terraform_plan
└── docs/                     # Documentación detallada
```

---

## Inicio rápido (5 minutos)

```bash
cd /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone

# 1. Dependencias
.venv/bin/pip install -r requirements.txt

# 2. Autenticación en Azure
az login
az account show --query id -o tsv          # copia este id

# 3. Configuración: pega el id en config.yaml -> azure.default_subscription_id
#    y ajusta terraform.working_dir

# 4. Verificación
.venv/bin/python -c "import server; print(server.get_server_configuration())"

# 5. Arranque manual (se queda esperando JSON-RPC por stdin: es lo correcto)
.venv/bin/python server.py
```

Registro en **Claude Desktop**
(`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "azure-landing-zone": {
      "command": "/Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/.venv/bin/python",
      "args": ["/Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/server.py"]
    }
  }
}
```

Detalles y alternativas en [docs/04-uso.md](docs/04-uso.md).

---

## Herramientas expuestas

| Herramienta | Qué hace | Requiere |
|---|---|---|
| `get_subscription_topology` | Mapa jerárquico por resource group + resumen agregado, optimizado en tokens | Rol *Reader* en Azure |
| `list_azure_resources` | Inventario plano con id ARM completo (filtrable por resource group) | Rol *Reader* en Azure |
| `list_untagged_resources` | Recursos sin ninguna etiqueta, ordenados por grupo | Rol *Reader* en Azure |
| `get_policy_compliance` | Estado Compliant/NonCompliant por política y recurso | Lectura en Policy Insights |
| `detect_infrastructure_drift` | `terraform plan -no-color -detailed-exitcode` | Terraform en el PATH + backend accesible |
| `get_server_configuration` | Configuración activa del servidor (diagnóstico) | — |

### Eficiencia en tokens

`get_subscription_topology` está diseñada para que Claude pueda analizar toda la
infraestructura sin saturar el contexto. Medido sobre una subscripción real de
42 resource groups y 1 634 recursos:

| Modo | Tokens aprox. |
|---|---|
| `include_resources=true` (detalle completo) | ~54 700 |
| `max_resources_per_group=5` | ~8 000 |
| `include_resources=false` (solo resumen) | **~3 076** |

Los contadores agregados son idénticos en los tres modos. La estrategia
recomendada es empezar por el resumen y bajar al detalle solo del grupo que
interese con `list_azure_resources`.

Referencia completa con formatos de entrada/salida en
[docs/03-herramientas.md](docs/03-herramientas.md).

---

## Estado actual del entorno

Comprobado el 2026-07-28 en esta máquina:

| Elemento | Estado |
|---|---|
| Dependencias Python | Instaladas en `.venv` (Python 3.14) |
| Azure CLI (`az`) | Instalado y con sesión iniciada |
| `terraform` | v1.15.8 instalado desde el tap `hashicorp/tap` |
| `terraform/` | Inicializado (`terraform init`) y con línea base aplicada → `SIN DRIFT` |
| `config.yaml` | Apuntando a la subscripción real y al directorio `terraform/` |

Las cinco herramientas se han ejecutado con éxito contra la subscripción real.

---

## Seguridad

- El servidor **no almacena credenciales**. Usa `DefaultAzureCredential`, que resuelve la
  identidad en cadena (variables de entorno → identidad administrada → Azure CLI → …).
- El navegador interactivo está deshabilitado (`exclude_interactive_browser_credential=True`)
  para que el proceso nunca se quede colgado esperando un login en un servidor sin interfaz.
- `terraform plan` se ejecuta con `shell=False` y lista de argumentos explícita: ninguna
  entrada del modelo puede inyectar comandos adicionales.
- Los logs van a **stderr**; stdout está reservado al protocolo MCP.
- `config.yaml` puede contener identificadores de subscripción: añádelo a `.gitignore` si el
  repositorio es público (ver `config.example.yaml` como plantilla versionable).
