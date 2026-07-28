# 5. Resolución de problemas

## 5.1 Diagnóstico en 3 pasos

```bash
cd /Users/juancarlosmartinez/PycharmProjects/mcp-azure-landing-zone

# 1. ¿Qué configuración está activa realmente?
.venv/bin/python -c "import server; print(server.get_server_configuration())"

# 2. ¿Hay sesión válida en Azure?
az account show --query "{sub:name, id:id, user:user.name}" -o json

# 3. ¿Responde ARM?
.venv/bin/python -c "import server; print(server.list_azure_resources()[:400])"
```

Los logs completos (con la traza de la excepción original) se escriben en
**stderr**. En Claude Desktop:

```bash
tail -f ~/Library/Logs/Claude/mcp-server-azure-landing-zone.log
```

---

## 5.2 Errores de Azure

### `SubscriptionNotFound`

```json
{"status": "error", "message": "Error al consultar Azure Resource Manager.",
 "detail": "(SubscriptionNotFound) The subscription '00000000-…' could not be found."}
```

**Causa:** `config.yaml` sigue con el GUID placeholder, o la identidad no tiene
acceso a esa subscripción.

**Solución:**

```bash
az account list --query "[].{name:name,id:id}" -o table   # id correcto
```

Pégalo en `azure.default_subscription_id`. Si el id es correcto, el problema es
de permisos: pide el rol *Reader* sobre esa subscripción.

---

### `Fallo de autenticación contra Azure`

**Causa:** no hay ninguna credencial válida en la cadena de `DefaultAzureCredential`.

**Solución, por orden:**

```bash
az login                     # opción más rápida en local
az account get-access-token  # verifica que el token se emite
```

Para service principal, comprueba que las tres variables están **exportadas en el
proceso del servidor** (no solo en tu shell):

```bash
env | grep AZURE_
```

Recuerda que Claude Desktop no hereda tu shell: declara las variables en el
bloque `env` de `claude_desktop_config.json`.

---

### `403 AuthorizationFailed` al consultar políticas

**Causa:** la consulta de Policy Insights requiere
`Microsoft.PolicyInsights/policyStates/queryResults/action`, que no siempre está
cubierto por el rol asignado.

**Solución:**

```bash
az role assignment create \
  --assignee "<appId-o-email>" \
  --role "Security Reader" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>"
```

También sirve *Resource Policy Contributor*. Las asignaciones de rol tardan unos
minutos en propagarse.

---

### `get_policy_compliance` devuelve `total_evaluations: 0`

No es un error. Causas habituales:

- No hay ninguna Azure Policy asignada al ámbito.
- Las políticas se asignaron hace menos de ~30 minutos y aún no se han evaluado.
- Las asignaciones están a nivel de management group y no han generado registros
  en esta subscripción.

Fuerza una evaluación (puede tardar bastante en completarse):

```bash
az policy state trigger-scan --subscription <SUBSCRIPTION_ID>
```

---

### La respuesta es enorme / se agota el contexto

Filtra por resource group:

> Lista solo los recursos de `rg-alz-hub-prod`

O sube los límites internos si de verdad los necesitas:

| Constante | Fichero | Valor por defecto |
|---|---|---|
| `MAX_DETAIL_RECORDS` | `tools/policy.py` | 100 registros no conformes |
| `MAX_OUTPUT_CHARS` | `tools/terraform.py` | 20 000 caracteres de salida |

---

## 5.3 Errores de Terraform

### `No se ha encontrado el ejecutable 'terraform' en el PATH`

**Estado actual de esta máquina: Terraform no está instalado.**

```bash
brew install terraform
terraform version
```

Si ya está instalado pero el servidor no lo encuentra, el problema es que el
cliente MCP arranca el proceso con un `PATH` mínimo. Declara el `PATH` completo
en el bloque `env` del cliente:

```json
"env": { "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" }
```

---

### `El directorio de trabajo '…' no existe`

`terraform.working_dir` apunta a una ruta inexistente. Corrígela en `config.yaml`
con la ruta **absoluta** del directorio que contiene tus `.tf`:

```bash
cd /ruta/a/tu/terraform && pwd
```

---

### `'terraform plan' falló con código 1`

Lee el bloque `--- ERRORES (stderr) ---` de la respuesta. Causas típicas:

| Mensaje de Terraform | Solución |
|---|---|
| `Backend initialization required` / `Module not installed` | `terraform init` en el directorio |
| `Error building ARM Config` / `building account` | Credenciales del proveedor `azurerm`: `az login` o variables `ARM_*` |
| `Error acquiring the state lock` | Otro proceso tiene el lock: espera o `terraform force-unlock <ID>` (con cuidado) |
| `No value for required variable` | Pasa el `.tfvars` con el parámetro `var_file` |
| `Error: Invalid provider configuration` | Revisa `provider "azurerm"` y la subscripción configurada en el código |

---

### `'terraform plan' superó el tiempo máximo`

Sube `terraform.timeout_seconds` en `config.yaml` (por ejemplo a `1800`).
Si tu cliente MCP corta antes por su propio timeout, ejecuta el plan fuera del
servidor y pídele a Claude que interprete la salida que le pegues.

---

## 5.4 Errores del servidor MCP

### El servidor no aparece en Claude Desktop

1. Valida el JSON (una coma sobrante lo rompe todo, y falla en silencio):
   ```bash
   python3 -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```
2. Comprueba que `command` es la ruta absoluta al Python del `.venv`.
3. Cierra Claude Desktop **por completo** (⌘Q) y vuelve a abrirlo.
4. Revisa el log: `~/Library/Logs/Claude/mcp-server-azure-landing-zone.log`.

---

### `ModuleNotFoundError: No module named 'mcp'` (o `azure`, o `yaml`)

Se está usando el Python del sistema en vez del del entorno virtual:

```bash
.venv/bin/pip install -r requirements.txt
```

y en la configuración del cliente apunta `command` a `.venv/bin/python`.

---

### `ModuleNotFoundError: No module named 'tools'`

Se ha invocado `server.py` desde un directorio distinto sin que su carpeta esté
en `sys.path`. Ejecuta siempre con la ruta absoluta del script
(`/ruta/.venv/bin/python /ruta/server.py`), que es como lo hace el cliente MCP.

---

### `TypeError: PolicyInsightsClient.__init__() missing 1 required positional argument`

La versión instalada de `azure-mgmt-policyinsights` exige `subscription_id` en el
constructor. El código ya lo pasa; si ves este error, tienes una copia antigua
del fichero. `tools/policy.py` debe contener:

```python
client = PolicyInsightsClient(credential, subscription_id)
```

---

### El cliente se desconecta nada más conectar

Casi siempre es porque **algo escribió en stdout**, que está reservado para el
protocolo JSON-RPC. Revisa que no haya ningún `print()` en el código: todo el
logging debe ir a stderr (ya está configurado así en `server.py`).

---

## 5.5 Cómo pedir ayuda

Si vas a reportar un problema, incluye:

1. Salida de `get_server_configuration` (censura el GUID si es sensible).
2. Salida de `az account show`.
3. Versiones: `.venv/bin/pip list | grep -Ei "mcp|azure|yaml"`.
4. Las últimas líneas del log de stderr con la traza completa.
