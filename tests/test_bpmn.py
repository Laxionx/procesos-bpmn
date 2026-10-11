"""Procedimientos en BPMN 2.0. Criterios fijados ANTES de correr:

- Cada .bpmn valida contra el XSD oficial de la OMG (BPMN 2.0, formal/2011-01-03).
- Reglas de modelado: inicio y fin, todo nodo alcanzable desde el inicio y con camino a un fin,
  salidas de las decisiones con nombre, sin flujos repetidos.
- Dibujo: formas sin solapes y dentro de su carril, flechas ortogonales que salen y llegan al
  borde de sus formas y que no atraviesan otras formas.
- Consistencia del XML: un BPMNShape por piscina, carril y nodo; un BPMNEdge por flujo; los
  carriles reparten los nodos sin repetir; incoming y outgoing cuadran con los flujos.
- Los .bpmn de salidas/ están al día con sus definiciones.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from lxml import etree

from procesos_bpmn.__main__ import main
from procesos_bpmn.bpmn import BPMN, BPMNDI, a_bpmn
from procesos_bpmn.diagrama import Caja, plano
from procesos_bpmn.modelo import DefinicionError, cargar
from procesos_bpmn.validar import _cruza, errores_xsd, problemas, problemas_dibujo
from procesos_bpmn.vista import svg

RAIZ = Path(__file__).resolve().parents[1]
DEFINICIONES = sorted((RAIZ / "definiciones").glob("*.yaml"))
XSD = Path(os.environ.get("BPMN_XSD_DIR", RAIZ / "xsd"))
NS = {"b": BPMN, "bpmndi": BPMNDI}


@pytest.fixture(params=DEFINICIONES, ids=lambda p: p.stem)
def proc(request):
    return cargar(request.param)


def test_hay_tres_procedimientos():
    assert len(DEFINICIONES) == 3


def test_reglas_de_modelado(proc):
    assert problemas(proc) == []


def test_dibujo(proc):
    assert problemas_dibujo(proc, plano(proc)) == []


@pytest.mark.skipif(not (XSD / "BPMN20.xsd").exists(), reason="faltan los XSD de la OMG")
def test_valida_contra_el_xsd_de_la_omg(proc):
    assert errores_xsd(a_bpmn(proc), XSD) == []


@pytest.mark.skipif(not (XSD / "BPMN20.xsd").exists(), reason="faltan los XSD de la OMG")
def test_el_xsd_rechaza_un_documento_roto(proc):
    doc = a_bpmn(proc).replace(b'targetRef="fin"', b"", 1)  # flujo sin destino
    assert errores_xsd(doc, XSD)


def test_xml_consistente(proc):
    root = etree.fromstring(a_bpmn(proc))
    process = root.find("b:process", NS)
    nodes = [e for e in process if e.get("id") in {n.id for n in proc.nodos}]
    assert len(nodes) == len(proc.nodos)
    flows = process.findall("b:sequenceFlow", NS)
    assert len(flows) == len(proc.flujos)
    refs = [r.text for r in process.findall("b:laneSet/b:lane/b:flowNodeRef", NS)]
    assert sorted(refs) == sorted(n.id for n in proc.nodos)
    for node in nodes:
        incoming = {e.text for e in node.findall("b:incoming", NS)}
        outgoing = {e.text for e in node.findall("b:outgoing", NS)}
        assert incoming == {f.get("id") for f in flows if f.get("targetRef") == node.get("id")}
        assert outgoing == {f.get("id") for f in flows if f.get("sourceRef") == node.get("id")}
    plane = root.find("bpmndi:BPMNDiagram/bpmndi:BPMNPlane", NS)
    shapes = plane.findall("bpmndi:BPMNShape", NS)
    assert len(shapes) == 1 + len(proc.carriles) + len(proc.nodos)
    assert len(plane.findall("bpmndi:BPMNEdge", NS)) == len(proc.flujos)
    ids = {e.get("id") for e in root.iter() if e.get("id")}
    assert all(s.get("bpmnElement") in ids for s in plane)
    timers = process.findall("b:intermediateCatchEvent/b:timerEventDefinition", NS)
    assert len(timers) == sum(n.tipo == "espera" for n in proc.nodos)


def test_salidas_al_dia(proc):
    archivo = RAIZ / "salidas" / f"{proc.id}.bpmn"
    assert archivo.read_bytes() == a_bpmn(proc), "regenere con: python -m procesos_bpmn generar"


def test_vista_previa(proc):
    root = etree.fromstring(svg(proc).encode("utf-8"))
    assert root.tag.endswith("svg")


BASE = """
id: prueba
nombre: Prueba
carriles: [Rol]
nodos:
  - {id: i, tipo: inicio, nombre: I, carril: Rol}
  - {id: m, tipo: decision, nombre: "", carril: Rol}
  - {id: g, tipo: decision, nombre: "¿Bien?", carril: Rol}
  - {id: t, tipo: tarea, nombre: T, carril: Rol}
  - {id: f, tipo: fin, nombre: F, carril: Rol}
flujos:
  - [i, m]
  - [m, g]
  - [g, t, "No"]
  - [t, m]
  - [g, f, "Sí"]
"""


def test_base_de_mutaciones_es_valida():
    proc = cargar(BASE)
    assert problemas(proc) == [] and problemas_dibujo(proc, plano(proc)) == []


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('[g, f, "Sí"]', "[t, t]", "fin"),  # el fin queda sin llegada
        ('[g, t, "No"]', "[g, t]", "nombre"),
        ("  - [i, m]\n", "  - [i, m]\n  - [t, i]\n", "inicio"),
        ("  - [i, m]\n", "  - [i, m]\n  - [i, m]\n", "repetidos"),
        ("  - [t, m]\n", "", "fin"),  # t no tiene salida ni camino a un fin
        ("  - [t, m]\n", "  - [t, g]\n", "combinar"),  # vuelta directa a la decisión (Bizagi)
    ],
)
def test_reglas_de_modelado_pueden_fallar(old, new, message):
    errores = problemas(cargar(BASE.replace(old, new)))
    assert any(message in e for e in errores), errores


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("carril: Rol}\n  - {id: m", "carril: Otro}\n  - {id: m", "carril"),
        ("{id: t, tipo: tarea", "{id: t, tipo: subproceso", "tipo"),
        ("{id: t,", "{id: 9t,", "id"),
        ("[t, m]", "[t, x]", "no existe"),
        ("{id: f,", "{id: g,", "repetidos"),
    ],
)
def test_errores_de_definicion(old, new, message):
    with pytest.raises(DefinicionError, match=message):
        cargar(BASE.replace(old, new))


def test_deteccion_de_cruces_y_solapes():
    caja = Caja(100, 100, 50, 50)
    assert _cruza((80, 120), (200, 120), caja)  # horizontal que pasa por dentro
    assert _cruza((125, 50), (125, 300), caja)  # vertical
    assert not _cruza((80, 90), (200, 90), caja)  # pasa por arriba
    assert not _cruza((100, 300), (100, 400), caja)
    assert caja.solapa(Caja(140, 140, 50, 50)) and not caja.solapa(Caja(150, 100, 10, 10))


def test_linea_de_comandos(tmp_path):
    assert main(["generar", str(RAIZ / "definiciones"), str(tmp_path)]) == 0
    assert len(list(tmp_path.glob("*.bpmn"))) == 3
    if (XSD / "BPMN20.xsd").exists():
        assert main(["validar", str(tmp_path), "--xsd", str(XSD)]) == 0
    roto = tmp_path / "def"
    roto.mkdir()
    (roto / "x.yaml").write_text(BASE.replace('[g, t, "No"]', "[g, t]"), encoding="utf-8")
    assert main(["generar", str(roto), str(tmp_path / "out")]) == 1
    assert main(["generar", str(tmp_path / "no_existe"), str(tmp_path / "o2")]) == 0


def test_yaml_mal_formado():
    with pytest.raises(DefinicionError, match="YAML"):
        cargar("id: x\nnodos: [{id: a, nombre: ¿mal?, tipo: tarea}")
