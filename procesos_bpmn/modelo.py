"""Procedimiento: carriles (roles), nodos y flujos, leídos de un YAML (ver ``definiciones/``)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# tipo en el YAML -> elemento BPMN 2.0
TIPOS = {
    "inicio": "startEvent",
    "fin": "endEvent",
    "tarea": "task",
    "tarea_usuario": "userTask",
    "tarea_manual": "manualTask",
    "tarea_servicio": "serviceTask",
    "decision": "exclusiveGateway",
    "paralelo": "parallelGateway",
    "espera": "intermediateCatchEvent",  # con temporizador
}
ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")  # xsd:ID (NCName)


class DefinicionError(ValueError):
    """El YAML del procedimiento no cumple el formato; el mensaje dice dónde."""


@dataclass(frozen=True)
class Nodo:
    id: str
    tipo: str
    nombre: str
    carril: str


@dataclass(frozen=True)
class Flujo:
    origen: str
    destino: str
    nombre: str = ""


@dataclass(frozen=True)
class Procedimiento:
    id: str
    nombre: str
    documentacion: str
    carriles: tuple[str, ...]
    nodos: tuple[Nodo, ...]
    flujos: tuple[Flujo, ...]

    def nodo(self, id_: str) -> Nodo:
        return next(n for n in self.nodos if n.id == id_)


def _id(value: Any, where: str) -> str:
    text = str(value)
    if not ID.match(text):
        raise DefinicionError(f"{where}: id {text!r} no válido (letras, dígitos, _ . -)")
    return text


def _nodo(data: Any, carriles: tuple[str, ...], index: int) -> Nodo:
    if not isinstance(data, Mapping):
        raise DefinicionError(f"nodo {index}: debe ser un mapa con id, tipo, nombre y carril")
    try:
        nodo = Nodo(
            _id(data["id"], f"nodo {index}"),
            str(data["tipo"]),
            str(data["nombre"]),
            str(data["carril"]),
        )
    except KeyError as error:
        raise DefinicionError(f"nodo {index}: falta {error.args[0]!r}") from error
    if nodo.tipo not in TIPOS:
        raise DefinicionError(f"nodo {nodo.id!r}: tipo {nodo.tipo!r}; use uno de {sorted(TIPOS)}")
    if nodo.carril not in carriles:
        raise DefinicionError(f"nodo {nodo.id!r}: el carril {nodo.carril!r} no está declarado")
    return nodo


def _flujo(data: Any, ids: set[str], index: int) -> Flujo:
    if not isinstance(data, list) or len(data) not in (2, 3):
        raise DefinicionError(
            f"flujo {index}: debe ser [origen, destino] o [origen, destino, nombre]"
        )
    flujo = Flujo(str(data[0]), str(data[1]), str(data[2]) if len(data) == 3 else "")
    for end in (flujo.origen, flujo.destino):
        if end not in ids:
            raise DefinicionError(f"flujo {index}: el nodo {end!r} no existe")
    return flujo


def cargar(fuente: str | Path) -> Procedimiento:
    """Lee un procedimiento desde la ruta de un ``.yaml`` o desde el texto YAML."""
    path = Path(str(fuente))
    text = path.read_text(encoding="utf-8") if path.suffix in (".yaml", ".yml") else str(fuente)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise DefinicionError(f"YAML mal formado: {error}") from error
    if not isinstance(data, Mapping):
        raise DefinicionError("El archivo debe ser un mapa YAML")
    try:
        carriles = tuple(str(c) for c in data["carriles"])
        nodos = tuple(_nodo(n, carriles, i) for i, n in enumerate(data["nodos"]))
        ids = {n.id for n in nodos}
        if len(ids) != len(nodos):
            raise DefinicionError("hay ids de nodo repetidos")
        flujos = tuple(_flujo(f, ids, i) for i, f in enumerate(data["flujos"]))
        return Procedimiento(
            _id(data["id"], "procedimiento"),
            str(data["nombre"]),
            str(data.get("documentacion", "")).strip(),
            carriles,
            nodos,
            flujos,
        )
    except KeyError as error:
        raise DefinicionError(f"procedimiento: falta {error.args[0]!r}") from error
