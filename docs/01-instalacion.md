# 1. Instalación

## 1.1 Requisitos previos

| Requisito | Versión mínima | Cómo comprobarlo | Cómo instalarlo (macOS) |
|---|---|---|---|
| Python | 3.10 | `python3 --version` | `brew install python@3.12` |
| Azure CLI | 2.50 | `az version` | `brew install azure-cli` |
| Terraform | 1.5 | `terraform version` | `brew install terraform` |
| Cliente MCP | — | — | Claude Desktop o Claude Code |

> **Terraform es opcional**: solo lo necesita la herramienta
> `detect_infrastructure_drift`. El resto funciona sin él. En esta máquina
> `terraform` **no está instalado** actualmente.

Además necesitas una **identidad de Azure** con permisos de lectura sobre la
subscripción (ver [02-configuracion.md](02-configuracion.md#25-permisos-necesarios-en-azure)).

---

## 1.2 Instalación de dependencias

El proyecto ya incluye un entorno virtual en `.venv`.

```bash
cd /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

Si prefieres crear el entorno desde cero:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Paquetes instalados

| Paquete | Para qué |
|---|---|
| `mcp` | Framework `FastMCP` y transporte stdio |
| `azure-identity` | `DefaultAzureCredential` (cadena de autenticación) |
| `azure-mgmt-resource` | Inventario de recursos ARM |
| `azure-mgmt-policyinsights` | Estados de cumplimiento de Azure Policy |
| `azure-core` | Excepciones y paginación comunes del SDK |
| `PyYAML` | Lectura de `config.yaml` |

---

## 1.3 Autenticación en Azure

La vía más simple en una máquina de desarrollo:

```bash
az login
az account set --subscription "<nombre-o-id-de-tu-subscripción>"
az account show --query "{name:name, id:id, tenant:tenantId}" -o json
```

`DefaultAzureCredential` reutilizará automáticamente esa sesión. Para entornos
desatendidos (CI, servidor) usa un *service principal*: ver
[02-configuracion.md](02-configuracion.md#24-métodos-de-autenticación).

---

## 1.4 Configuración mínima

```bash
cp config.example.yaml config.yaml   # si aún no existe config.yaml
```

Edita `config.yaml` y rellena, como mínimo:

- `azure.default_subscription_id` → el GUID que devolvió `az account show --query id -o tsv`
- `terraform.working_dir` → ruta absoluta al directorio con tus `.tf`

Detalle campo a campo en [02-configuracion.md](02-configuracion.md).

---

## 1.5 Verificación de la instalación

### a) Configuración cargada correctamente

```bash
.venv/bin/python -c "import server; print(server.get_server_configuration())"
```

Salida esperada:

```json
{
  "status": "ok",
  "config_path": ".../config.yaml",
  "config_exists": true,
  "azure": { "default_subscription_id": "77308696-..." },
  "terraform": { "working_dir": "/ruta/...", "timeout_seconds": 600 }
}
```

### b) Herramientas registradas

```bash
.venv/bin/python -c "
import asyncio, server
print([t.name for t in asyncio.run(server.mcp.list_tools())])
"
```

Salida esperada:

```
['list_azure_resources', 'list_untagged_resources', 'get_policy_compliance',
 'detect_infrastructure_drift', 'get_server_configuration']
```

### c) Conectividad real con Azure

```bash
.venv/bin/python -c "
import json, server
r = json.loads(server.list_azure_resources())
print(r['status'], r.get('count', r.get('message')))
"
```

`ok` seguido de un número → todo correcto.
`error` → consulta [05-troubleshooting.md](05-troubleshooting.md).

### d) Arranque del servidor

```bash
.venv/bin/python server.py
```

Debe imprimir en stderr una línea `Iniciando 'Azure Landing Zone Assistant'…` y
quedarse **bloqueado esperando entrada**. Eso es lo correcto: está escuchando
JSON-RPC por stdin. Ciérralo con `Ctrl+C`.

---

## 1.6 Siguiente paso

Registra el servidor en tu cliente MCP siguiendo [04-uso.md](04-uso.md).
