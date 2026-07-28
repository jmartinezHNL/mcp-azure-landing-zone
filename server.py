"""Servidor MCP "Azure Landing Zone Assistant".

Expone por stdio un conjunto de herramientas que permiten a un asistente de IA
inspeccionar recursos de Azure, evaluar el cumplimiento de Azure Policy y
detectar drift de infraestructura con Terraform.

Ejecución:
    python server.py
"""

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

import yaml
from mcp.server.fastmcp import FastMCP

from tools.policy import get_policy_states as _get_policy_states
from tools.resources import get_untagged_resources as _get_untagged_resources
from tools.resources import list_resources as _list_resources
from tools.terraform import DEFAULT_TIMEOUT_SECONDS
from tools.terraform import run_terraform_plan as _run_terraform_plan

# El transporte stdio reserva stdout para el protocolo MCP: todo log debe ir a stderr.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("mcp-azure-landing-zone")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("MCP_ALZ_CONFIG", os.path.join(BASE_DIR, "config.yaml"))

DEFAULT_CONFIG: Dict[str, Any] = {
    "azure": {"default_subscription_id": ""},
    "terraform": {"working_dir": "", "timeout_seconds": DEFAULT_TIMEOUT_SECONDS},
}


def load_config(path: str = CONFIG_PATH) -> Dict[str, Any]:
    """Carga config.yaml devolviendo valores por defecto ante cualquier fallo."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError("El contenido de config.yaml no es un mapa YAML.")
    except FileNotFoundError:
        logger.warning("No se encontró %s; se usará la configuración por defecto.", path)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    except (yaml.YAMLError, OSError, ValueError) as exc:
        logger.error("No se pudo leer %s (%s); se usará la configuración por defecto.", path, exc)
        return json.loads(json.dumps(DEFAULT_CONFIG))

    config = json.loads(json.dumps(DEFAULT_CONFIG))
    for section, values in data.items():
        if isinstance(values, dict) and isinstance(config.get(section), dict):
            config[section].update(values)
        else:
            config[section] = values

    # Las variables de entorno tienen prioridad sobre el fichero.
    env_subscription = os.environ.get("AZURE_SUBSCRIPTION_ID")
    if env_subscription:
        config["azure"]["default_subscription_id"] = env_subscription
    env_tf_dir = os.environ.get("TERRAFORM_WORKING_DIR")
    if env_tf_dir:
        config["terraform"]["working_dir"] = env_tf_dir

    return config


CONFIG = load_config()

mcp = FastMCP("Azure Landing Zone Assistant")


def _resolve_subscription(subscription_id: Optional[str]) -> str:
    """Devuelve la subscripción indicada o, en su defecto, la de config.yaml."""
    if subscription_id:
        return subscription_id.strip()
    return str(CONFIG.get("azure", {}).get("default_subscription_id") or "").strip()


def _resolve_working_dir(working_dir: Optional[str]) -> str:
    """Devuelve el directorio Terraform indicado o el configurado por defecto."""
    if working_dir:
        return working_dir.strip()
    return str(CONFIG.get("terraform", {}).get("working_dir") or "").strip()


@mcp.tool()
def list_azure_resources(
    subscription_id: Optional[str] = None,
    resource_group: Optional[str] = None,
) -> str:
    """Lista los recursos desplegados en una subscripción de Azure.

    Úsala cuando el usuario pregunte qué hay desplegado en la Landing Zone, qué
    recursos contiene un resource group concreto, en qué regiones están o de qué
    tipo son (máquinas virtuales, storage accounts, redes virtuales, etc.).

    Args:
        subscription_id: Id de la subscripción de Azure. Si se omite, se usa la
            subscripción por defecto definida en config.yaml.
        resource_group: Nombre del resource group para acotar la búsqueda. Si se
            omite, se listan los recursos de toda la subscripción.

    Returns:
        JSON en texto con el número total de recursos y, por cada uno, su nombre,
        tipo, región, resource group, etiquetas e id ARM completo.
    """
    subscription = _resolve_subscription(subscription_id)
    if not subscription:
        return json.dumps(
            {
                "status": "error",
                "message": (
                    "No hay subscripción disponible: indique subscription_id o "
                    "configure azure.default_subscription_id en config.yaml."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    return _list_resources(subscription, resource_group)


@mcp.tool()
def list_untagged_resources(subscription_id: Optional[str] = None) -> str:
    """Identifica los recursos de Azure que no tienen ninguna etiqueta (tag).

    Úsala para auditar el gobierno de la Landing Zone: los recursos sin tags
    incumplen normalmente las políticas de asignación de centro de coste,
    propietario o entorno, y dificultan la imputación de gasto.

    Args:
        subscription_id: Id de la subscripción de Azure. Si se omite, se usa la
            subscripción por defecto definida en config.yaml.

    Returns:
        JSON en texto con el total de recursos analizados, cuántos y qué
        porcentaje carecen de etiquetas, y el detalle de cada recurso afectado.
    """
    subscription = _resolve_subscription(subscription_id)
    if not subscription:
        return json.dumps(
            {
                "status": "error",
                "message": (
                    "No hay subscripción disponible: indique subscription_id o "
                    "configure azure.default_subscription_id en config.yaml."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    return _get_untagged_resources(subscription)


@mcp.tool()
def get_policy_compliance(subscription_id: Optional[str] = None) -> str:
    """Evalúa el cumplimiento de las Azure Policies de una subscripción.

    Úsala cuando el usuario pregunte por el estado de seguridad o cumplimiento
    normativo de la Landing Zone, qué políticas se están incumpliendo, qué
    recursos son no conformes (NonCompliant) o cuál es el porcentaje global de
    cumplimiento. Los datos proceden de Azure Policy Insights (estado 'latest').

    Args:
        subscription_id: Id de la subscripción de Azure. Si se omite, se usa la
            subscripción por defecto definida en config.yaml.

    Returns:
        JSON en texto con el total de evaluaciones, el porcentaje de
        cumplimiento, el recuento por estado (Compliant / NonCompliant), el
        desglose por asignación de política y el detalle de recursos no conformes.
    """
    subscription = _resolve_subscription(subscription_id)
    if not subscription:
        return json.dumps(
            {
                "status": "error",
                "message": (
                    "No hay subscripción disponible: indique subscription_id o "
                    "configure azure.default_subscription_id en config.yaml."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    return _get_policy_states(subscription)


@mcp.tool()
def detect_infrastructure_drift(
    working_dir: Optional[str] = None,
    var_file: Optional[str] = None,
) -> str:
    """Detecta drift de infraestructura ejecutando 'terraform plan' en local.

    Úsala cuando el usuario quiera saber si la infraestructura real de Azure se
    ha desviado del código Terraform que define la Landing Zone, o qué cambios
    aplicaría un despliegue. La operación es de solo lectura: nunca aplica
    cambios (no ejecuta 'terraform apply').

    Args:
        working_dir: Directorio con la configuración de Terraform. Si se omite,
            se usa terraform.working_dir de config.yaml.
        var_file: Ruta opcional a un fichero .tfvars con variables de entrada.

    Returns:
        Texto con el veredicto ('SIN DRIFT' o 'DRIFT DETECTADO'), el código de
        salida y la salida completa de Terraform con los recursos a crear,
        modificar o destruir.
    """
    directory = _resolve_working_dir(working_dir)
    if not directory:
        return (
            "ERROR: No hay directorio Terraform disponible. Indique working_dir o "
            "configure terraform.working_dir en config.yaml."
        )

    try:
        timeout = int(CONFIG.get("terraform", {}).get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS

    return _run_terraform_plan(directory, timeout_seconds=timeout, var_file=var_file)


@mcp.tool()
def get_server_configuration() -> str:
    """Muestra la configuración activa del servidor MCP.

    Úsala para comprobar qué subscripción de Azure y qué directorio de Terraform
    se están utilizando por defecto antes de ejecutar el resto de herramientas.

    Returns:
        JSON en texto con la ruta del fichero de configuración, la subscripción
        por defecto y la configuración de Terraform.
    """
    return json.dumps(
        {
            "status": "ok",
            "config_path": CONFIG_PATH,
            "config_exists": os.path.isfile(CONFIG_PATH),
            "azure": CONFIG.get("azure", {}),
            "terraform": CONFIG.get("terraform", {}),
        },
        indent=2,
        ensure_ascii=False,
    )


def main() -> None:
    """Arranca el servidor MCP sobre el transporte stdio."""
    logger.info("Iniciando 'Azure Landing Zone Assistant' (configuración: %s)", CONFIG_PATH)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
