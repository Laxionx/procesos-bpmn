"""Trazado automático del diagrama (BPMNDI): un piscina horizontal con un carril por rol.

- Los flujos de vuelta (los que cierran un ciclo de corrección) se detectan con una búsqueda en
  profundidad desde el inicio y no cuentan para ordenar.
- Cada nodo va en la columna de su camino más largo desde el inicio, dentro de su carril; si dos
  nodos de un carril caen en la misma columna, el carril crece hacia abajo.
- Flechas ortogonales: hacia adelante entran por la izquierda del destino. Las de vuelta salen por
  la derecha, suben por el pasillo entre columnas y bajan por el pasillo antes del destino.
- Si una compuerta tiene dos salidas hacia el mismo lado, la más cercana usa el vértice de ese
  lado y la otra el derecho.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .modelo import TIPOS, Procedimiento

TAREA = (110.0, 60.0)
TAMANOS = {
    "startEvent": (36.0, 36.0),
    "endEvent": (36.0, 36.0),
    "intermediateCatchEvent": (36.0, 36.0),
    "exclusiveGateway": (50.0, 50.0),
    "parallelGateway": (50.0, 50.0),
}
ORIGEN = 30.0
ETIQUETA_PISCINA, ETIQUETA_CARRIL = 30.0, 30.0
COLUMNA, FILA, MARGEN = 160.0, 120.0, 40.0
Punto = tuple[float, float]


@dataclass(frozen=True)
class Caja:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def solapa(self, otra: Caja) -> bool:
        return not (
            self.right <= otra.x or otra.right <= self.x
            or self.bottom <= otra.y or otra.bottom <= self.y
        )  # fmt: skip


@dataclass(frozen=True)
class Plano:
    piscina: Caja
    carriles: dict[str, Caja]
    formas: dict[str, Caja]
    vueltas: frozenset[int]  # índices de los flujos de vuelta
    rutas: tuple[tuple[Punto, ...], ...]  # una por flujo, en orden


def flujos_de_vuelta(proc: Procedimiento) -> frozenset[int]:
    salidas: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for i, f in enumerate(proc.flujos):
        salidas[f.origen].append((i, f.destino))
    vueltas: set[int] = set()
    estado: dict[str, int] = {}  # 1 en la pila, 2 terminado

    def visitar(nodo: str) -> None:
        estado[nodo] = 1
        for i, destino in salidas[nodo]:
            if estado.get(destino) == 1:
                vueltas.add(i)
            elif destino not in estado:
                visitar(destino)
        estado[nodo] = 2

    for n in proc.nodos:
        if n.tipo == "inicio" and n.id not in estado:
            visitar(n.id)
    return frozenset(vueltas)


def columnas(proc: Procedimiento, vueltas: frozenset[int]) -> dict[str, int]:
    adelante = [f for i, f in enumerate(proc.flujos) if i not in vueltas]
    entradas = {n.id: 0 for n in proc.nodos}
    for f in adelante:
        entradas[f.destino] += 1
    columna = {n.id: 0 for n in proc.nodos}
    listos = [n.id for n in proc.nodos if entradas[n.id] == 0]
    while listos:
        nodo = listos.pop(0)
        for f in adelante:
            if f.origen == nodo:
                columna[f.destino] = max(columna[f.destino], columna[nodo] + 1)
                entradas[f.destino] -= 1
                if entradas[f.destino] == 0:
                    listos.append(f.destino)
    return columna


def plano(proc: Procedimiento) -> Plano:
    vueltas = flujos_de_vuelta(proc)
    columna = columnas(proc, vueltas)
    fila: dict[str, int] = {}
    ocupadas: dict[tuple[str, int], int] = defaultdict(int)
    for n in proc.nodos:
        fila[n.id] = ocupadas[(n.carril, columna[n.id])]
        ocupadas[(n.carril, columna[n.id])] += 1
    filas = {
        c: max([v for (k, _), v in ocupadas.items() if k == c], default=1) for c in proc.carriles
    }
    ancho = ETIQUETA_PISCINA + ETIQUETA_CARRIL + 2 * MARGEN + (max(columna.values()) + 1) * COLUMNA
    carriles, y = {}, ORIGEN
    for c in proc.carriles:
        carriles[c] = Caja(ORIGEN + ETIQUETA_PISCINA, y, ancho - ETIQUETA_PISCINA, filas[c] * FILA)
        y += filas[c] * FILA
    piscina = Caja(ORIGEN, ORIGEN, ancho, y - ORIGEN)
    formas = {}
    for n in proc.nodos:
        w, h = TAMANOS.get(TIPOS[n.tipo], TAREA)
        cx = ORIGEN + ETIQUETA_PISCINA + ETIQUETA_CARRIL + MARGEN + columna[n.id] * COLUMNA + 55
        cy = carriles[n.carril].y + (fila[n.id] + 0.5) * FILA
        formas[n.id] = Caja(cx - w / 2.0, cy - h / 2.0, w, h)
    laterales = _salidas_laterales(proc, formas, vueltas)
    rutas = tuple(
        _ruta(formas[f.origen], formas[f.destino], i in vueltas, i in laterales,
              proc.nodo(f.origen).tipo)
        for i, f in enumerate(proc.flujos)
    )  # fmt: skip
    return Plano(piscina, carriles, formas, vueltas, rutas)


def _salidas_laterales(
    proc: Procedimiento, formas: dict[str, Caja], vueltas: frozenset[int]
) -> frozenset[int]:
    """Flujos de compuerta que salen por el vértice derecho porque otro, más cercano, ya usa el
    de arriba (o el de abajo)."""
    grupos: dict[tuple[str, bool], list[tuple[float, int]]] = defaultdict(list)
    for i, f in enumerate(proc.flujos):
        s, t = formas[f.origen], formas[f.destino]
        if proc.nodo(f.origen).tipo in ("decision", "paralelo") and i not in vueltas:
            if abs(s.cy - t.cy) >= 0.5:
                grupos[(f.origen, t.cy > s.cy)].append((abs(t.cy - s.cy), i))
    return frozenset(i for g in grupos.values() for _, i in sorted(g)[1:])


def _ruta(s: Caja, t: Caja, vuelta: bool, lateral: bool, tipo_origen: str) -> tuple[Punto, ...]:
    if vuelta:  # sube por el pasillo tras el origen y baja por el pasillo antes del destino
        pasillo, entrada = s.cx + TAREA[0] / 2.0 + 20.0, t.cx - TAREA[0] / 2.0 - 30.0
        arriba = min(s.y, t.y) - 16.0
        return (
            (s.right, s.cy), (pasillo, s.cy), (pasillo, arriba),
            (entrada, arriba), (entrada, t.cy), (t.x, t.cy),
        )  # fmt: skip
    if abs(s.cy - t.cy) < 0.5:
        return ((s.right, s.cy), (t.x, t.cy))
    if tipo_origen in ("decision", "paralelo") and not lateral:  # vértice de arriba o de abajo
        borde = s.bottom if t.cy > s.cy else s.y
        return ((s.cx, borde), (s.cx, t.cy), (t.x, t.cy))
    quiebre = t.x - 20.0
    return ((s.right, s.cy), (quiebre, s.cy), (quiebre, t.cy), (t.x, t.cy))
