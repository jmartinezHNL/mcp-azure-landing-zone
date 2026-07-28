"""Inspección de recursos de Azure Resource Manager (ARM).

Las funciones de este módulo devuelven estructuras nativas de Python (``dict`` /
``list``) en lugar de texto: la serialización a JSON es responsabilidad de
``server.py``.

El diseño prioriza la eficiencia en tokens: se recorre la subscripción en una
sola pasada paginada, se conservan únicamente los metadatos esenciales de cada
recurso y se omiten los campos vacíos.
"""

import logging
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    HttpResponseError,
)
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient

logger = logging.getLogger(__name__)

# Prefijo de proveedor que se recorta del campo "type" para ahorrar tokens:
# "Microsoft.Network/virtualNetworks" -> "Network/virtualNetworks".
# Los proveedores de terceros conservan su namespace completo.
_AZURE_PROVIDER_PREFIX = "Microsoft."

# Etiquetas de gobierno que se consideran "principales" y se conservan siempre.
# La comparación es insensible a mayúsculas, guiones y guiones bajos.
ESSENTIAL_TAG_KEYS: Tuple[str, ...] = (
    "environment",
    "env",
    "owner",
    "costcenter",
    "project",
    "application",
    "app",
    "businessunit",
    "criticality",
    "managedby",
)

# Tope de etiquetas por recurso cuando no se filtra por ESSENTIAL_TAG_KEYS.
MAX_TAGS_PER_RESOURCE = 5

# Nº de tipos de recurso distintos que se listan en el resumen global.
TOP_RESOURCE_TYPES = 15

# Clave usada para los recursos cuyo id ARM no incluye resource group.
_ORPHAN_GROUP = "(sin-resource-group)"


# --------------------------------------------------------------------------- #
# Utilidades internas
# --------------------------------------------------------------------------- #
def _build_client(subscription_id: str) -> ResourceManagementClient:
    """Crea un ``ResourceManagementClient`` autenticado.

    ``DefaultAzureCredential`` resuelve la identidad en cadena: variables de
    entorno, workload identity, identidad administrada y Azure CLI. El navegador
    interactivo queda excluido para no bloquear un proceso sin interfaz.
    """
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return ResourceManagementClient(credential, subscription_id)


def _error(exc: Exception, context: str) -> Dict[str, str]:
    """Traduce una excepción del SDK a un error legible para el asistente."""
    if isinstance(exc, ClientAuthenticationError):
        message = (
            "Fallo de autenticación contra Azure. Ejecute 'az login' o configure "
            "las credenciales del service principal (AZURE_TENANT_ID, "
            "AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)."
        )
    elif isinstance(exc, HttpResponseError) and exc.status_code == 403:
        message = (
            "Permisos insuficientes: la identidad actual necesita al menos el rol "
            "'Reader' sobre la subscripción."
        )
    elif isinstance(exc, HttpResponseError) and exc.status_code == 404:
        message = "El ámbito consultado no existe o no es visible para esta identidad."
    elif isinstance(exc, AzureError):
        message = f"Error de conectividad o de la API de Azure al {context}."
    else:
        message = f"Error inesperado al {context}."

    return {"status": "error", "message": message, "detail": str(exc)}


def _normalize_tag_key(key: str) -> str:
    """Normaliza una clave de etiqueta para compararla con ESSENTIAL_TAG_KEYS."""
    return key.lower().replace("-", "").replace("_", "").replace(" ", "")


def _essential_tags(tags: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Filtra las etiquetas a las de gobierno, con un tope de seguridad.

    Devuelve las coincidencias con :data:`ESSENTIAL_TAG_KEYS`; si el recurso no
    tiene ninguna de ellas, conserva las primeras :data:`MAX_TAGS_PER_RESOURCE`
    para no perder por completo el contexto.
    """
    if not tags:
        return {}

    essential = {
        key: value
        for key, value in tags.items()
        if _normalize_tag_key(key) in ESSENTIAL_TAG_KEYS
    }
    if essential:
        return essential

    return dict(list(tags.items())[:MAX_TAGS_PER_RESOURCE])


def _short_type(resource_type: Optional[str]) -> str:
    """Acorta el tipo ARM quitando el prefijo 'Microsoft.' del proveedor.

    La comparación ignora mayúsculas porque ARM devuelve indistintamente
    'Microsoft.Insights/...' y 'microsoft.insights/...'.
    """
    if not resource_type:
        return "desconocido"
    if resource_type.lower().startswith(_AZURE_PROVIDER_PREFIX.lower()):
        return resource_type[len(_AZURE_PROVIDER_PREFIX):]
    return resource_type


def _resource_group_from_id(resource_id: str) -> str:
    """Extrae el nombre del resource group de un id ARM (sin distinguir mayúsculas)."""
    if not resource_id:
        return ""
    parts = resource_id.split("/")
    for index, part in enumerate(parts):
        if part.lower() == "resourcegroups" and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def _compact_resource(resource: Any, group_location: Optional[str] = None) -> Dict[str, Any]:
    """Reduce un recurso ARM a sus metadatos esenciales.

    Omite los campos vacíos y la ubicación cuando coincide con la del resource
    group, ya que es el caso mayoritario y aporta poca información.
    """
    compact: Dict[str, Any] = {
        "name": getattr(resource, "name", None),
        "type": _short_type(getattr(resource, "type", None)),
    }

    location = getattr(resource, "location", None)
    if location and location != group_location:
        compact["location"] = location

    tags = _essential_tags(getattr(resource, "tags", None))
    if tags:
        compact["tags"] = tags

    return compact


def _iter_resources(client: ResourceManagementClient) -> Iterable[Any]:
    """Itera todos los recursos de la subscripción resolviendo la paginación."""
    return client.resources.list()


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def get_full_subscription_topology(
    subscription_id: str,
    include_resources: bool = True,
    max_resources_per_group: Optional[int] = None,
) -> Dict[str, Any]:
    """Devuelve la topología completa de una subscripción jerarquizada por grupo.

    Recorre la subscripción en una sola pasada y organiza los recursos por
    resource group, conservando solo nombre, tipo, ubicación y etiquetas de
    gobierno. Incluye un resumen agregado para que el asistente pueda razonar
    sobre el conjunto sin leer el detalle completo.

    Args:
        subscription_id: GUID de la subscripción de Azure.
        include_resources: Si es ``False``, cada grupo se reduce a su recuento y
            a su desglose por tipo. Es el modo recomendado como primera consulta
            en subscripciones grandes: reduce la salida en torno a un 95 %.
        max_resources_per_group: Tope de recursos detallados por grupo. Los
            grupos recortados se marcan con ``resources_truncated``.

    Returns:
        Diccionario con ``status``, ``summary`` y ``resource_groups``; si algo
        falla, un diccionario con ``status='error'``, ``message`` y ``detail``.
    """
    if not subscription_id:
        return {
            "status": "error",
            "message": "No se ha indicado un subscription_id válido.",
        }

    groups: Dict[str, Dict[str, Any]] = {}
    locations: Counter = Counter()
    type_counter: Counter = Counter()
    total_resources = 0
    untagged = 0

    try:
        client = _build_client(subscription_id)

        # Los resource groups se leen primero para conocer su ubicación y sus
        # etiquetas, y para que aparezcan aunque estén vacíos.
        for group in client.resource_groups.list():
            name = getattr(group, "name", None)
            if not name:
                continue
            entry: Dict[str, Any] = {
                "location": getattr(group, "location", None),
                "resource_count": 0,
                "types": {},
                "resources": [],
            }
            group_tags = _essential_tags(getattr(group, "tags", None))
            if group_tags:
                entry["tags"] = group_tags
            groups[name] = entry

        for resource in _iter_resources(client):
            total_resources += 1
            group_name = _resource_group_from_id(getattr(resource, "id", "") or "")
            if not group_name:
                group_name = _ORPHAN_GROUP

            group_entry = groups.setdefault(
                group_name,
                {"location": None, "resource_count": 0, "types": {}, "resources": []},
            )

            compact = _compact_resource(resource, group_entry.get("location"))
            group_entry["resource_count"] += 1
            group_entry["types"][compact["type"]] = (
                group_entry["types"].get(compact["type"], 0) + 1
            )
            if not compact.get("tags"):
                untagged += 1

            if include_resources:
                if (
                    max_resources_per_group is None
                    or len(group_entry["resources"]) < max_resources_per_group
                ):
                    group_entry["resources"].append(compact)
                else:
                    group_entry["resources_truncated"] = True

            type_counter[compact["type"]] += 1
            resource_location = getattr(resource, "location", None)
            if resource_location:
                locations[resource_location] += 1
    except Exception as exc:  # noqa: BLE001 - la herramienta nunca debe romper el servidor
        logger.exception("Fallo al construir la topología de la subscripción.")
        return _error(exc, "recorrer los recursos de la subscripción")

    # Sin detalle, la lista vacía solo aportaría ruido.
    if not include_resources:
        for group in groups.values():
            group.pop("resources", None)

    # Los grupos se ordenan de mayor a menor tamaño: lo relevante va primero.
    ordered_groups = dict(
        sorted(groups.items(), key=lambda item: item[1]["resource_count"], reverse=True)
    )

    return {
        "status": "ok",
        "subscription_id": subscription_id,
        "summary": {
            "total_resource_groups": len(groups),
            "total_resources": total_resources,
            "empty_resource_groups": sum(
                1 for group in groups.values() if group["resource_count"] == 0
            ),
            "resources_without_essential_tags": untagged,
            "locations": dict(locations.most_common()),
            "top_resource_types": dict(type_counter.most_common(TOP_RESOURCE_TYPES)),
            "distinct_resource_types": len(type_counter),
        },
        "detail_level": "completo" if include_resources else "solo-resumen",
        "notes": (
            "El campo 'type' omite el prefijo 'Microsoft.'. La ubicación de un "
            "recurso solo se indica cuando difiere de la de su resource group. "
            "Las etiquetas se filtran a las de gobierno."
        ),
        "resource_groups": ordered_groups,
    }


def get_untagged_resources(subscription_id: str) -> List[Dict[str, Any]]:
    """Lista los recursos sin etiquetas de una subscripción.

    Un recurso se considera sin etiquetar cuando carece de tags o su diccionario
    de tags está vacío, lo que suele indicar incumplimiento de las políticas de
    gobierno de la Landing Zone (propietario, centro de coste, entorno).

    Args:
        subscription_id: GUID de la subscripción de Azure.

    Returns:
        Lista de diccionarios con ``name``, ``type``, ``location``,
        ``resource_group`` e ``id``. Si se produce un error, la lista contiene
        un único elemento con las claves ``status``, ``message`` y ``detail``.
    """
    if not subscription_id:
        return [
            {
                "status": "error",
                "message": "No se ha indicado un subscription_id válido.",
            }
        ]

    untagged: List[Dict[str, Any]] = []

    try:
        client = _build_client(subscription_id)
        for resource in _iter_resources(client):
            if getattr(resource, "tags", None):
                continue
            resource_id = getattr(resource, "id", "") or ""
            untagged.append(
                {
                    "name": getattr(resource, "name", None),
                    "type": _short_type(getattr(resource, "type", None)),
                    "location": getattr(resource, "location", None),
                    "resource_group": _resource_group_from_id(resource_id),
                    "id": resource_id,
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo al buscar recursos sin etiquetas.")
        return [_error(exc, "buscar recursos sin etiquetas")]

    untagged.sort(key=lambda item: (item["resource_group"] or "", item["name"] or ""))
    return untagged


def list_resources(
    subscription_id: str, resource_group: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Lista los recursos de una subscripción, opcionalmente filtrados por grupo.

    Vista plana y detallada, complementaria a
    :func:`get_full_subscription_topology`: conserva el id ARM completo, útil
    cuando hace falta identificar un recurso de forma inequívoca.

    Args:
        subscription_id: GUID de la subscripción de Azure.
        resource_group: Nombre del resource group a filtrar. Si es ``None`` se
            recorre la subscripción completa.

    Returns:
        Lista de diccionarios con ``name``, ``type``, ``location``,
        ``resource_group``, ``tags`` e ``id``. Si se produce un error, la lista
        contiene un único elemento con las claves ``status``, ``message`` y
        ``detail``.
    """
    if not subscription_id:
        return [
            {
                "status": "error",
                "message": "No se ha indicado un subscription_id válido.",
            }
        ]

    resources: List[Dict[str, Any]] = []

    try:
        client = _build_client(subscription_id)
        if resource_group:
            iterator: Iterable[Any] = client.resources.list_by_resource_group(
                resource_group
            )
        else:
            iterator = _iter_resources(client)

        for resource in iterator:
            resource_id = getattr(resource, "id", "") or ""
            resources.append(
                {
                    "name": getattr(resource, "name", None),
                    "type": _short_type(getattr(resource, "type", None)),
                    "location": getattr(resource, "location", None),
                    "resource_group": resource_group
                    or _resource_group_from_id(resource_id),
                    "tags": getattr(resource, "tags", None) or {},
                    "id": resource_id,
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo al listar recursos.")
        return [_error(exc, "listar los recursos")]

    return resources
