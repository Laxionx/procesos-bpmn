"""Escritura del procedimiento como BPMN 2.0 XML (OMG, formal/2011-01-03), con su diagrama.

Estructura: una colaboración con una piscina (participante) que apunta al proceso; el proceso
lleva un conjunto de carriles, los nodos con sus flujos de entrada y salida, y los flujos de
secuencia. El diagrama (BPMNDI) tiene una forma por piscina, carril y nodo, y una arista por flujo.
"""

from __future__ import annotations

from lxml import etree

from .diagrama import Plano, plano
from .modelo import TIPOS, Procedimiento

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
DC = "http://www.omg.org/spec/DD/20100524/DC"
DI = "http://www.omg.org/spec/DD/20100524/DI"
NSMAP = {None: BPMN, "bpmndi": BPMNDI, "dc": DC, "di": DI}
EXPORTADOR = "procesos-bpmn"
VERSION = "0.1.0"


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _flujo_id(i: int) -> str:
    return f"Flujo_{i + 1}"


def _bounds(parent: etree._Element, caja) -> None:
    etree.SubElement(
        parent, _q(DC, "Bounds"),
        x=f"{caja.x:.0f}", y=f"{caja.y:.0f}", width=f"{caja.w:.0f}", height=f"{caja.h:.0f}",
    )  # fmt: skip


def _proceso(defs: etree._Element, proc: Procedimiento) -> None:
    process = etree.SubElement(
        defs, _q(BPMN, "process"), id=f"Proceso_{proc.id}", name=proc.nombre, isExecutable="false"
    )
    if proc.documentacion:
        etree.SubElement(process, _q(BPMN, "documentation")).text = proc.documentacion
    lane_set = etree.SubElement(process, _q(BPMN, "laneSet"), id=f"Carriles_{proc.id}")
    for i, carril in enumerate(proc.carriles):
        lane = etree.SubElement(lane_set, _q(BPMN, "lane"), id=f"Carril_{i + 1}", name=carril)
        for n in proc.nodos:
            if n.carril == carril:
                etree.SubElement(lane, _q(BPMN, "flowNodeRef")).text = n.id
    for n in proc.nodos:
        node = etree.SubElement(process, _q(BPMN, TIPOS[n.tipo]), id=n.id, name=n.nombre)
        for i, f in enumerate(proc.flujos):
            if f.destino == n.id:
                etree.SubElement(node, _q(BPMN, "incoming")).text = _flujo_id(i)
        for i, f in enumerate(proc.flujos):
            if f.origen == n.id:
                etree.SubElement(node, _q(BPMN, "outgoing")).text = _flujo_id(i)
        if n.tipo == "espera":
            etree.SubElement(node, _q(BPMN, "timerEventDefinition"), id=f"Temporizador_{n.id}")
    for i, f in enumerate(proc.flujos):
        attrs = {"id": _flujo_id(i), "sourceRef": f.origen, "targetRef": f.destino}
        if f.nombre:
            attrs["name"] = f.nombre
        etree.SubElement(process, _q(BPMN, "sequenceFlow"), attrs)


def _diagrama(defs: etree._Element, proc: Procedimiento, dibujo: Plano) -> None:
    diagram = etree.SubElement(defs, _q(BPMNDI, "BPMNDiagram"), id=f"Diagrama_{proc.id}")
    plane = etree.SubElement(
        diagram, _q(BPMNDI, "BPMNPlane"), id=f"Plano_{proc.id}", bpmnElement=f"Colab_{proc.id}"
    )
    shape = etree.SubElement(
        plane, _q(BPMNDI, "BPMNShape"), id=f"Piscina_{proc.id}_di",
        bpmnElement=f"Piscina_{proc.id}", isHorizontal="true",
    )  # fmt: skip
    _bounds(shape, dibujo.piscina)
    for i, carril in enumerate(proc.carriles):
        shape = etree.SubElement(
            plane, _q(BPMNDI, "BPMNShape"), id=f"Carril_{i + 1}_di",
            bpmnElement=f"Carril_{i + 1}", isHorizontal="true",
        )  # fmt: skip
        _bounds(shape, dibujo.carriles[carril])
    for n in proc.nodos:
        attrs = {"id": f"{n.id}_di", "bpmnElement": n.id}
        if n.tipo == "decision":
            attrs["isMarkerVisible"] = "true"
        shape = etree.SubElement(plane, _q(BPMNDI, "BPMNShape"), attrs)
        _bounds(shape, dibujo.formas[n.id])
    for i, ruta in enumerate(dibujo.rutas):
        edge = etree.SubElement(
            plane, _q(BPMNDI, "BPMNEdge"), id=f"{_flujo_id(i)}_di", bpmnElement=_flujo_id(i)
        )
        for x, y in ruta:
            etree.SubElement(edge, _q(DI, "waypoint"), x=f"{x:.0f}", y=f"{y:.0f}")


def a_bpmn(proc: Procedimiento) -> bytes:
    """El procedimiento como documento BPMN 2.0 (UTF-8)."""
    defs = etree.Element(
        _q(BPMN, "definitions"), nsmap=NSMAP, id=f"Definiciones_{proc.id}",
        targetNamespace=f"urn:procesos-bpmn:{proc.id}", exporter=EXPORTADOR,
        exporterVersion=VERSION,
    )  # fmt: skip
    collab = etree.SubElement(defs, _q(BPMN, "collaboration"), id=f"Colab_{proc.id}")
    etree.SubElement(
        collab, _q(BPMN, "participant"), id=f"Piscina_{proc.id}", name=proc.nombre,
        processRef=f"Proceso_{proc.id}",
    )  # fmt: skip
    _proceso(defs, proc)
    _diagrama(defs, proc, plano(proc))
    return etree.tostring(defs, xml_declaration=True, encoding="UTF-8", pretty_print=True)
