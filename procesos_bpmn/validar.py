"""Validaciones: reglas de estructura del procedimiento, del dibujo y el XSD oficial de la OMG."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from lxml import etree

from .diagrama import Caja, Plano
from .modelo import Procedimiento

TOLERANCIA = 0.5  # px


def _alcanzables(inicios: list[str], vecinos: dict[str, list[str]]) -> set[str]:
    vistos, pila = set(inicios), list(inicios)
    while pila:
        for v in vecinos[pila.pop()]:
            if v not in vistos:
                vistos.add(v)
                pila.append(v)
    return vistos


def problemas(proc: Procedimiento) -> list[str]:
    """Reglas de buen modelado BPMN; lista vacía si el procedimiento las cumple."""
    salen, entran = defaultdict(list), defaultdict(list)
    for f in proc.flujos:
        salen[f.origen].append(f.destino)
        entran[f.destino].append(f.origen)
    inicios = [n.id for n in proc.nodos if n.tipo == "inicio"]
    fines = [n.id for n in proc.nodos if n.tipo == "fin"]
    errores = []
    if not inicios or not fines:
        errores.append("debe tener al menos un evento de inicio y uno de fin")
    for n in proc.nodos:
        if n.tipo == "inicio" and entran[n.id]:
            errores.append(f"{n.id}: el inicio no puede tener flujos de entrada")
        if n.tipo == "fin" and salen[n.id]:
            errores.append(f"{n.id}: el fin no puede tener flujos de salida")
        if n.tipo != "inicio" and not entran[n.id]:
            errores.append(f"{n.id}: no le llega ningún flujo")
        if n.tipo != "fin" and not salen[n.id]:
            errores.append(f"{n.id}: no sale ningún flujo")
        if n.tipo in ("decision", "paralelo") and len(entran[n.id]) > 1 and len(salen[n.id]) > 1:
            errores.append(f"{n.id}: una compuerta debe dividir o combinar, no ambas cosas")
        if n.tipo == "decision" and len(salen[n.id]) > 1:
            sin_nombre = [f.destino for f in proc.flujos if f.origen == n.id and not f.nombre]
            if sin_nombre:
                errores.append(f"{n.id}: las salidas de una decisión deben tener nombre")
    pares = [(f.origen, f.destino) for f in proc.flujos]
    if len(set(pares)) != len(pares):
        errores.append("hay flujos repetidos")
    perdidos = {n.id for n in proc.nodos} - _alcanzables(inicios, salen)
    if perdidos:
        errores.append(f"no se llega desde el inicio a {sorted(perdidos)}")
    sin_salida = {n.id for n in proc.nodos} - _alcanzables(fines, entran)
    if sin_salida:
        errores.append(f"desde {sorted(sin_salida)} no se llega a ningún fin")
    return errores


def _en_borde(p: tuple[float, float], c: Caja) -> bool:
    x, y = p
    dentro = c.x - TOLERANCIA <= x <= c.right + TOLERANCIA and (
        c.y - TOLERANCIA <= y <= c.bottom + TOLERANCIA
    )
    borde = min(abs(x - c.x), abs(x - c.right), abs(y - c.y), abs(y - c.bottom)) <= TOLERANCIA
    return dentro and borde


def problemas_dibujo(proc: Procedimiento, dibujo: Plano) -> list[str]:
    errores = []
    ids = [n.id for n in proc.nodos]
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if dibujo.formas[a].solapa(dibujo.formas[b]):
                errores.append(f"{a} y {b} se solapan")
    for n in proc.nodos:
        forma, carril = dibujo.formas[n.id], dibujo.carriles[n.carril]
        if not (carril.x <= forma.x and forma.right <= carril.right):
            errores.append(f"{n.id} se sale de su carril a lo ancho")
        if not (carril.y <= forma.y and forma.bottom <= carril.bottom):
            errores.append(f"{n.id} se sale de su carril a lo alto")
    for f, ruta in zip(proc.flujos, dibujo.rutas, strict=True):
        if not _en_borde(ruta[0], dibujo.formas[f.origen]):
            errores.append(f"{f.origen}→{f.destino}: no sale del borde de {f.origen}")
        if not _en_borde(ruta[-1], dibujo.formas[f.destino]):
            errores.append(f"{f.origen}→{f.destino}: no llega al borde de {f.destino}")
        for (x1, y1), (x2, y2) in zip(ruta, ruta[1:], strict=False):
            if abs(x1 - x2) > TOLERANCIA and abs(y1 - y2) > TOLERANCIA:
                errores.append(f"{f.origen}→{f.destino}: tramo en diagonal")
            for n in proc.nodos:
                if n.id not in (f.origen, f.destino) and _cruza(
                    (x1, y1), (x2, y2), dibujo.formas[n.id]
                ):
                    errores.append(f"{f.origen}→{f.destino}: atraviesa {n.id}")
    errores += _salidas_superpuestas(proc, dibujo)
    return errores


def _salidas_superpuestas(proc: Procedimiento, dibujo: Plano) -> list[str]:
    """Dos flujos del mismo origen no pueden compartir su primer tramo."""
    errores = []
    pares = list(zip(proc.flujos, dibujo.rutas, strict=True))
    for i, (fa, ra) in enumerate(pares):
        for fb, rb in pares[i + 1 :]:
            if fa.origen != fb.origen or ra[0] != rb[0]:
                continue
            (xa, ya), (xb, yb) = ra[1], rb[1]
            misma_vertical = abs(xa - ra[0][0]) <= TOLERANCIA and abs(xb - rb[0][0]) <= TOLERANCIA
            misma_horizontal = abs(ya - ra[0][1]) <= TOLERANCIA and abs(yb - rb[0][1]) <= TOLERANCIA
            mismo_sentido = (xa - ra[0][0]) * (xb - rb[0][0]) + (ya - ra[0][1]) * (
                yb - rb[0][1]
            ) > 0
            if (misma_vertical or misma_horizontal) and mismo_sentido:
                errores.append(
                    f"{fa.origen}: dos salidas superpuestas ({fa.destino}, {fb.destino})"
                )
    return errores


def _cruza(a: tuple[float, float], b: tuple[float, float], c: Caja) -> bool:
    """Un tramo horizontal o vertical que pasa por el interior de la caja."""
    (x1, y1), (x2, y2) = a, b
    if abs(y1 - y2) <= TOLERANCIA:
        return c.y < y1 < c.bottom and min(x1, x2) < c.right and max(x1, x2) > c.x
    return c.x < x1 < c.right and min(y1, y2) < c.bottom and max(y1, y2) > c.y


def errores_xsd(documento: bytes, carpeta_xsd: Path) -> list[str]:
    """Valida contra BPMN20.xsd de la OMG (con Semantic, BPMNDI, DC y DI en la misma carpeta)."""
    esquema = etree.XMLSchema(etree.parse(str(carpeta_xsd / "BPMN20.xsd")))
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    arbol = etree.fromstring(documento, parser)
    if esquema.validate(arbol):
        return []
    return [f"línea {e.line}: {e.message}" for e in esquema.error_log]
