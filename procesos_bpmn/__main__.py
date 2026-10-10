"""Uso:

python -m procesos_bpmn generar definiciones salidas
python -m procesos_bpmn validar salidas --xsd xsd
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .bpmn import a_bpmn
from .diagrama import plano
from .modelo import DefinicionError, cargar
from .validar import errores_xsd, problemas, problemas_dibujo


def _generar(origen: Path, destino: Path) -> int:
    destino.mkdir(parents=True, exist_ok=True)
    fallos = 0
    for archivo in sorted(origen.glob("*.yaml")):
        proc = cargar(archivo)
        errores = problemas(proc) + problemas_dibujo(proc, plano(proc))
        if errores:
            fallos += 1
            print(f"{archivo.name}: " + "; ".join(errores), file=sys.stderr)
            continue
        salida = destino / f"{proc.id}.bpmn"
        salida.write_bytes(a_bpmn(proc))
        print(f"{archivo.name} -> {salida}  ({len(proc.nodos)} nodos, {len(proc.flujos)} flujos)")
    return 1 if fallos else 0


def _validar(carpeta: Path, xsd: Path) -> int:
    fallos = 0
    for archivo in sorted(carpeta.glob("*.bpmn")):
        errores = errores_xsd(archivo.read_bytes(), xsd)
        fallos += bool(errores)
        print(f"{archivo.name}: {'válido contra el XSD de la OMG' if not errores else errores}")
    return 1 if fallos else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="procesos_bpmn", description="Procedimientos en BPMN 2.0")
    comandos = parser.add_subparsers(dest="comando", required=True)
    generar = comandos.add_parser("generar", help="YAML -> .bpmn")
    generar.add_argument("origen", type=Path)
    generar.add_argument("destino", type=Path)
    validar = comandos.add_parser("validar", help="Valida los .bpmn contra el XSD de la OMG")
    validar.add_argument("carpeta", type=Path)
    validar.add_argument("--xsd", type=Path, required=True)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if args.comando == "generar":
            return _generar(args.origen, args.destino)
        return _validar(args.carpeta, args.xsd)
    except (DefinicionError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
