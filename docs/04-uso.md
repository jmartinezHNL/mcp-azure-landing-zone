# 4. Uso: registro en el cliente y ejemplos

Rutas usadas en los ejemplos (ajústalas si mueves el proyecto):

```
PROYECTO = /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone
PYTHON   = /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/.venv/bin/python
SERVIDOR = /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/server.py
```

> Usa **siempre rutas absolutas** y el intérprete del `.venv`. El cliente MCP
> arranca el proceso sin tu shell interactivo: ni el `PATH` ni el entorno virtual
> activado se heredan.

---

## 4.1 Claude Desktop

Fichero de configuración en macOS:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

```json
{
  "mcpServers": {
    "azure-landing-zone": {
      "command": "/Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/.venv/bin/python",
      "args": ["/Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/server.py"],
      "env": {
        "AZURE_SUBSCRIPTION_ID": "77308696-6250-4529-8d8d-66944e6f5f38",
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
      }
    }
  }
}
```

Puntos clave del bloque `env`:

- `AZURE_SUBSCRIPTION_ID` es **opcional**: si ya está en `config.yaml`, puedes omitirlo.
- `PATH` sí conviene declararlo: es la forma de que el servidor encuentre los
  binarios `terraform` y `az`, que en macOS suelen estar en `/opt/homebrew/bin`.

Guarda el fichero y **reinicia Claude Desktop por completo**. Las herramientas
aparecerán en el icono de herramientas (🔨) de la ventana de chat.

---

## 4.2 Claude Code (CLI)

```bash
claude mcp add azure-landing-zone \
  --scope user \
  -- /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/.venv/bin/python \
     /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/server.py
```

| Scope | Alcance |
|---|---|
| `--scope local` | Solo tú, solo en este proyecto (por defecto) |
| `--scope project` | Se guarda en `.mcp.json` y se comparte con el equipo por git |
| `--scope user` | Tú, en todos tus proyectos |

Comprobación:

```bash
claude mcp list
claude mcp get azure-landing-zone
```

Alternativa por fichero, `.mcp.json` en la raíz del repo:

```json
{
  "mcpServers": {
    "azure-landing-zone": {
      "command": ".venv/bin/python",
      "args": ["server.py"]
    }
  }
}
```

---

## 4.3 Depuración con MCP Inspector

Para probar las herramientas sin pasar por Claude:

```bash
npx @modelcontextprotocol/inspector \
  /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/.venv/bin/python \
  /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone/server.py
```

Abre la URL que imprime, pulsa *Connect* → *List Tools* y ejecuta cada
herramienta con sus parámetros desde la interfaz.

### Invocación directa desde Python (sin cliente MCP)

```bash
cd /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone

.venv/bin/python -c "import server; print(server.get_server_configuration())"
.venv/bin/python -c "import server; print(server.get_subscription_topology(include_resources=False))"
.venv/bin/python -c "import server; print(server.list_azure_resources(resource_group='rg-alz-hub-prod'))"
.venv/bin/python -c "import server; print(server.list_untagged_resources())"
.venv/bin/python -c "import server; print(server.get_policy_compliance())"
.venv/bin/python -c "import server; print(server.detect_infrastructure_drift())"
```

Comparar el coste en tokens de los tres modos de topología:

```bash
.venv/bin/python - <<'PY'
import json
from tools.resources import get_full_subscription_topology as topo
SUB = "<TU_SUBSCRIPTION_ID>"
for etiqueta, kwargs in [
    ("completo", {}),
    ("max 5/grupo", {"max_resources_per_group": 5}),
    ("solo-resumen", {"include_resources": False}),
]:
    n = len(json.dumps(topo(SUB, **kwargs), ensure_ascii=False))
    print(f"{etiqueta:14} -> {n:>7} chars  (~{n // 4:>6} tokens)")
PY
```

---

## 4.4 Prompts de ejemplo

### Topología e inventario

> Dame un mapa de mi Landing Zone: cuántos resource groups hay y qué contiene cada uno.

> ¿Cuáles son los 5 resource groups más grandes y qué tipo de recursos predominan
> en cada uno?

> ¿En qué regiones tengo recursos y cuántos hay en cada una?

> Lista los recursos del resource group `rg-alz-hub-prod` con sus ids completos.

> Compara los recursos de la subscripción `77308696-…` con los de la
> `11111111-…` y dime qué hay en una que no esté en la otra.

### Gobierno y etiquetado

> Audita el etiquetado: ¿qué porcentaje de recursos no tiene tags y cuáles son
> los más críticos?

> Dame la lista de recursos sin etiquetar agrupada por resource group, y propón
> un script de `az cli` para etiquetarlos con `owner` y `costCenter`.

### Cumplimiento

> ¿Cuál es el estado de cumplimiento de mis Azure Policies?

> ¿Qué políticas se están incumpliendo y qué recursos concretos las incumplen?

> Prioriza los incumplimientos por criticidad y proponme un plan de remediación
> en tres fases.

### Drift de infraestructura

> ¿Hay drift entre mi código Terraform y la infraestructura real?

> Ejecuta el plan con el fichero de variables `prod.tfvars` y explícame en
> lenguaje llano qué cambiaría.

> Si hay drift, dime si lo correcto es actualizar el código o revertir el cambio
> manual hecho en el portal.

### Auditoría combinada

> Hazme una auditoría completa de la Landing Zone: inventario, etiquetado,
> cumplimiento de políticas y drift. Resúmelo en un informe con hallazgos
> ordenados por severidad y acciones recomendadas.

---

## 4.5 Flujo de trabajo recomendado

1. **`get_server_configuration`** — confirma subscripción y directorio activos.
2. **`get_subscription_topology(include_resources=False)`** — mapa global barato en tokens.
3. **`list_azure_resources(resource_group=…)`** — baja al detalle solo del grupo relevante.
4. **`list_untagged_resources`** — detecta huecos de gobierno.
5. **`get_policy_compliance`** — mide el cumplimiento de seguridad.
6. **`detect_infrastructure_drift`** — comprueba si el código refleja la realidad.

Pídele a Claude que encadene los pasos y produzca un único informe; tiene todas
las herramientas disponibles en la misma conversación.

---

## 4.6 Buenas prácticas

- **Empieza por el resumen.** `get_subscription_topology(include_resources=False)`
  cuesta ~3 000 tokens frente a los ~55 000 del detalle completo en una
  subscripción de 1 600 recursos, y responde la mayoría de preguntas globales.
- **Acota antes de listar.** En subscripciones grandes, filtra por
  `resource_group` para no llenar la ventana de contexto con cientos de recursos.
- **El drift tarda.** `terraform plan` hace refresh contra Azure; en landing zones
  grandes puede superar el timeout del cliente. Sube `terraform.timeout_seconds`
  o segmenta la configuración.
- **Los datos de Policy no son instantáneos.** Reflejan el último ciclo de
  evaluación (~24 h). Fuerza un escaneo con
  `az policy state trigger-scan --subscription <id>` si necesitas datos frescos.
- **Una instancia por entorno.** Registra `alz-prod` y `alz-dev` como servidores
  separados con distinto `MCP_ALZ_CONFIG` en lugar de cambiar la subscripción a mano.
- **Revisa los logs en stderr** cuando algo falle: llevan la traza completa de la
  excepción original.
