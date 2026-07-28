"""Herramientas de inspección de recursos de Azure Resource Manager (ARM).

Todas las funciones públicas devuelven una cadena con JSON serializado para que
un modelo de lenguaje pueda interpretar el resultado sin post-procesado.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from azure.core.exceptions import AzureError, ClientAuthenticationError
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient

logger = logging.getLogger(__name__)


def _error(message: str, detail: str = "") -> str:
    """Serializa un error en JSON con la forma esperada por el cliente MCP."""
    payload: Dict[str, Any] = {"status": "error", "message": message}
    if detail:
        payload["detail"] = detail
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _ok(payload: Dict[str, Any]) -> str:
    """Serializa una respuesta correcta en JSON."""
    payload = {"status": "ok", **payload}
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _build_client(subscription_id: str) -> ResourceManagementClient:
    """Crea un ResourceManagementClient autenticado con DefaultAzureCredential.

    DefaultAzureCredential resuelve la identidad en cadena: variables de entorno,
    identidad administrada, Azure CLI, Azure Developer CLI, etc.
    """
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return ResourceManagementClient(credential, subscription_id)


def _resource_group_from_id(resource_id: str) -> str:
    """Extrae el nombre del resource group a partir del id ARM del recurso."""
    parts = resource_id.split("/")
    try:
        return parts[parts.index("resourceGroups") + 1]
    except (ValueError, IndexError):
        return ""


def _serialize(resource: Any) -> Dict[str, Any]:
    """Normaliza un objeto GenericResourceExpanded a un diccionario plano."""
    resource_id = getattr(resource, "id", "") or ""
    return {
        "name": getattr(resource, "name", None),
        "type": getattr(resource, "type", None),
        "location": getattr(resource, "location", None),
        "resource_group": _resource_group_from_id(resource_id),
        "tags": getattr(resource, "tags", None) or {},
        "id": resource_id,
    }


def list_resources(subscription_id: str, resource_group: Optional[str] = None) -> str:
    """Lista los recursos de una subscripción, opcionalmente filtrados por grupo.

    Args:
        subscription_id: Identificador de la subscripción de Azure.
        resource_group: Nombre del resource group a filtrar. Si es ``None`` se
            recorre la subscripción completa.

    Returns:
        Cadena JSON con el número de recursos y su detalle, o con el error.
    """
    if not subscription_id:
        return _error("No se ha indicado un subscription_id válido.")

    try:
        client = _build_client(subscription_id)
        if resource_group:
            iterator = client.resources.list_by_resource_group(resource_group)
        else:
            iterator = client.resources.list()

        resources: List[Dict[str, Any]] = [_serialize(item) for item in iterator]
    except ClientAuthenticationError as exc:
        logger.exception("Fallo de autenticación contra Azure.")
        return _error(
            "Fallo de autenticación contra Azure. Ejecute 'az login' o configure "
            "las credenciales de servicio.",
            str(exc),
        )
    except AzureError as exc:
        logger.exception("Error del SDK de Azure al listar recursos.")
        return _error("Error al consultar Azure Resource Manager.", str(exc))
    except Exception as exc:  # noqa: BLE001 - la herramienta nunca debe romper el servidor
        logger.exception("Error inesperado al listar recursos.")
        return _error("Error inesperado al listar recursos.", str(exc))

    return _ok(
        {
            "subscription_id": subscription_id,
            "resource_group": resource_group,
            "count": len(resources),
            "resources": resources,
        }
    )


def get_untagged_resources(subscription_id: str) -> str:
    """Devuelve los recursos de la subscripción que no tienen ninguna etiqueta.

    Un recurso se considera sin etiquetar cuando su diccionario de tags está
    vacío o ausente, lo que suele indicar incumplimiento de la política de
    gobierno de la Landing Zone (centro de coste, propietario, entorno...).

    Args:
        subscription_id: Identificador de la subscripción de Azure.

    Returns:
        Cadena JSON con los recursos sin tags y su porcentaje sobre el total.
    """
    if not subscription_id:
        return _error("No se ha indicado un subscription_id válido.")

    try:
        client = _build_client(subscription_id)
        total = 0
        untagged: List[Dict[str, Any]] = []

        for item in client.resources.list():
            total += 1
            if not getattr(item, "tags", None):
                untagged.append(_serialize(item))
    except ClientAuthenticationError as exc:
        logger.exception("Fallo de autenticación contra Azure.")
        return _error(
            "Fallo de autenticación contra Azure. Ejecute 'az login' o configure "
            "las credenciales de servicio.",
            str(exc),
        )
    except AzureError as exc:
        logger.exception("Error del SDK de Azure al buscar recursos sin tags.")
        return _error("Error al consultar Azure Resource Manager.", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error inesperado al buscar recursos sin tags.")
        return _error("Error inesperado al buscar recursos sin tags.", str(exc))

    percentage = round(len(untagged) / total * 100, 2) if total else 0.0

    return _ok(
        {
            "subscription_id": subscription_id,
            "total_resources": total,
            "untagged_count": len(untagged),
            "untagged_percentage": percentage,
            "untagged_resources": untagged,
        }
    )
