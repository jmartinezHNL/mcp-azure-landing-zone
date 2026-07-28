"""Herramientas de cumplimiento basadas en Azure Policy Insights."""

import json
import logging
from collections import Counter
from typing import Any, Dict, List

from azure.core.exceptions import AzureError, ClientAuthenticationError
from azure.identity import DefaultAzureCredential
from azure.mgmt.policyinsights import PolicyInsightsClient

logger = logging.getLogger(__name__)

# Número máximo de registros de incumplimiento que se devuelven en detalle para
# evitar respuestas gigantescas en subscripciones grandes.
MAX_DETAIL_RECORDS = 100


def _error(message: str, detail: str = "") -> str:
    """Serializa un error en JSON con la forma esperada por el cliente MCP."""
    payload: Dict[str, Any] = {"status": "error", "message": message}
    if detail:
        payload["detail"] = detail
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _serialize(state: Any) -> Dict[str, Any]:
    """Normaliza un PolicyState a un diccionario plano y legible."""
    return {
        "resource_id": getattr(state, "resource_id", None),
        "resource_type": getattr(state, "resource_type", None),
        "resource_group": getattr(state, "resource_group", None),
        "compliance_state": getattr(state, "compliance_state", None),
        "policy_definition_id": getattr(state, "policy_definition_id", None),
        "policy_definition_action": getattr(state, "policy_definition_action", None),
        "policy_assignment_name": getattr(state, "policy_assignment_name", None),
        "policy_set_definition_name": getattr(state, "policy_set_definition_name", None),
        "is_compliant": getattr(state, "is_compliant", None),
    }


def get_policy_states(subscription_id: str) -> str:
    """Obtiene el estado de cumplimiento de Azure Policy en una subscripción.

    Consulta el último estado conocido (``latest``) de Policy Insights y agrega
    los resultados por estado de cumplimiento y por asignación de política.

    Args:
        subscription_id: Identificador de la subscripción de Azure.

    Returns:
        Cadena JSON con el resumen de cumplimiento y el detalle de los recursos
        no conformes, o con el error producido.
    """
    if not subscription_id:
        return _error("No se ha indicado un subscription_id válido.")

    try:
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        client = PolicyInsightsClient(credential, subscription_id)

        states = list(
            client.policy_states.list_query_results_for_subscription(
                policy_states_resource="latest",
                subscription_id=subscription_id,
            )
        )
    except ClientAuthenticationError as exc:
        logger.exception("Fallo de autenticación contra Azure.")
        return _error(
            "Fallo de autenticación contra Azure. Ejecute 'az login' o configure "
            "las credenciales de servicio.",
            str(exc),
        )
    except AzureError as exc:
        logger.exception("Error del SDK de Azure al consultar Policy Insights.")
        return _error("Error al consultar Azure Policy Insights.", str(exc))
    except Exception as exc:  # noqa: BLE001 - la herramienta nunca debe romper el servidor
        logger.exception("Error inesperado al consultar Policy Insights.")
        return _error("Error inesperado al consultar Policy Insights.", str(exc))

    summary: Counter = Counter()
    by_assignment: Dict[str, Counter] = {}
    non_compliant: List[Dict[str, Any]] = []

    for state in states:
        record = _serialize(state)
        compliance = record["compliance_state"] or "Unknown"
        summary[compliance] += 1

        assignment = record["policy_assignment_name"] or "sin-asignacion"
        by_assignment.setdefault(assignment, Counter())[compliance] += 1

        if compliance.lower() == "noncompliant":
            non_compliant.append(record)

    total = sum(summary.values())
    compliant = summary.get("Compliant", 0)
    compliance_rate = round(compliant / total * 100, 2) if total else 0.0

    payload = {
        "status": "ok",
        "subscription_id": subscription_id,
        "total_evaluations": total,
        "compliance_rate_percent": compliance_rate,
        "summary": dict(summary),
        "by_policy_assignment": {
            name: dict(counts) for name, counts in by_assignment.items()
        },
        "non_compliant_count": len(non_compliant),
        "non_compliant_truncated": len(non_compliant) > MAX_DETAIL_RECORDS,
        "non_compliant_resources": non_compliant[:MAX_DETAIL_RECORDS],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
