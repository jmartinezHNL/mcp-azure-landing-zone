"""Herramienta de detección de drift mediante Terraform en local."""

import logging
import os
import shutil
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)

# Códigos de salida de "terraform plan -detailed-exitcode".
EXIT_NO_CHANGES = 0
EXIT_ERROR = 1
EXIT_CHANGES_PRESENT = 2

DEFAULT_TIMEOUT_SECONDS = 600

# Límite de caracteres de salida para no saturar la ventana de contexto.
MAX_OUTPUT_CHARS = 20000


def _truncate(text: str) -> str:
    """Recorta la salida por el principio conservando el resumen final del plan."""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    omitted = len(text) - MAX_OUTPUT_CHARS
    return (
        f"[... {omitted} caracteres omitidos del inicio de la salida ...]\n"
        + text[-MAX_OUTPUT_CHARS:]
    )


def run_terraform_plan(
    working_dir: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    var_file: Optional[str] = None,
) -> str:
    """Ejecuta ``terraform plan -no-color`` y devuelve la salida como texto.

    El comando se lanza sin shell y con la lista de argumentos explícita, de modo
    que ningún valor de entrada pueda inyectar comandos adicionales.

    Args:
        working_dir: Directorio que contiene la configuración de Terraform.
        timeout_seconds: Tiempo máximo de ejecución antes de abortar el proceso.
        var_file: Ruta opcional a un fichero ``.tfvars`` a pasar con ``-var-file``.

    Returns:
        Texto con el veredicto de drift y la salida de Terraform, o el error.
    """
    if not working_dir:
        return "ERROR: No se ha indicado el directorio de trabajo de Terraform."

    working_dir = os.path.abspath(os.path.expanduser(working_dir))

    if not os.path.isdir(working_dir):
        return f"ERROR: El directorio de trabajo '{working_dir}' no existe."

    terraform_bin = shutil.which("terraform")
    if terraform_bin is None:
        return (
            "ERROR: No se ha encontrado el ejecutable 'terraform' en el PATH. "
            "Instale Terraform o añádalo al PATH del proceso del servidor MCP."
        )

    command: List[str] = [
        terraform_bin,
        "plan",
        "-no-color",
        "-input=false",
        "-detailed-exitcode",
    ]

    if var_file:
        var_file_path = os.path.abspath(os.path.expanduser(var_file))
        if not os.path.isfile(var_file_path):
            return f"ERROR: El fichero de variables '{var_file_path}' no existe."
        command.append(f"-var-file={var_file_path}")

    try:
        completed = subprocess.run(
            command,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        logger.exception("Timeout ejecutando terraform plan.")
        return (
            f"ERROR: 'terraform plan' superó el tiempo máximo de "
            f"{timeout_seconds} segundos y fue abortado."
        )
    except OSError as exc:
        logger.exception("Error del sistema operativo ejecutando terraform plan.")
        return f"ERROR: No se pudo ejecutar 'terraform plan': {exc}"
    except Exception as exc:  # noqa: BLE001 - la herramienta nunca debe romper el servidor
        logger.exception("Error inesperado ejecutando terraform plan.")
        return f"ERROR inesperado al ejecutar 'terraform plan': {exc}"

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode == EXIT_NO_CHANGES:
        verdict = "SIN DRIFT: la infraestructura coincide con la configuración."
    elif completed.returncode == EXIT_CHANGES_PRESENT:
        verdict = "DRIFT DETECTADO: hay cambios pendientes entre el estado y el código."
    else:
        verdict = (
            f"ERROR: 'terraform plan' falló con código {completed.returncode}. "
            "Revise si el directorio está inicializado ('terraform init') y si "
            "las credenciales del proveedor azurerm son válidas."
        )

    sections = [
        f"Directorio: {working_dir}",
        f"Comando: {' '.join(command)}",
        f"Código de salida: {completed.returncode}",
        verdict,
    ]
    if stdout:
        sections.append("--- SALIDA (stdout) ---\n" + _truncate(stdout))
    if stderr:
        sections.append("--- ERRORES (stderr) ---\n" + _truncate(stderr))
    if not stdout and not stderr:
        sections.append("Terraform no ha devuelto salida.")

    return "\n\n".join(sections)
