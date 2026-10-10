"""Vista previa en SVG con las mismas coordenadas que el BPMNDI (lo que verá Bizagi al importar).

Sigue la notación BPMN: eventos en círculo (el de fin con borde grueso), tareas redondeadas,
compuertas en rombo (X exclusiva, + paralela) y temporizador con reloj.
"""

from __future__ import annotations

from html import escape

from .diagrama import Caja, plano
from .modelo import Procedimiento

TINTA, LINEA, FONDO = "#1d232a", "#9aa3ad", "#ffffff"


def _texto(
    x: float, y: float, texto: str, ancho: float, tam: int = 11, ancla: str = "middle"
) -> str:
    """Texto centrado en varias líneas, cortado por palabras para caber en `ancho`."""
    por_linea = max(int(ancho / (tam * 0.55)), 6)
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if len(prueba) > por_linea and actual:
            lineas.append(actual)
            actual = palabra
        else:
            actual = prueba
    lineas.append(actual)
    y0 = y - (len(lineas) - 1) * tam * 0.6
    spans = "".join(
        f'<tspan x="{x:.0f}" y="{y0 + i * tam * 1.2:.0f}">{escape(t)}</tspan>'
        for i, t in enumerate(lineas)
    )
    return f'<text font-size="{tam}" text-anchor="{ancla}">{spans}</text>'


def _forma(tipo: str, c: Caja, nombre: str) -> str:
    if tipo in ("inicio", "fin", "espera"):
        r = c.w / 2.0
        borde = {"inicio": 1.5, "fin": 3.5, "espera": 1.5}[tipo]
        extra = ""
        if tipo == "espera":
            extra = (
                f'<circle cx="{c.cx}" cy="{c.cy}" r="{r - 4}" fill="none" stroke="{TINTA}"/>'
                f'<path d="M{c.cx},{c.cy - 8} V{c.cy} L{c.cx + 6},{c.cy + 4}" fill="none" '
                f'stroke="{TINTA}"/>'
            )
        return (
            f'<circle cx="{c.cx}" cy="{c.cy}" r="{r}" fill="{FONDO}" stroke="{TINTA}" '
            f'stroke-width="{borde}"/>{extra}' + _texto(c.cx, c.bottom + 16, nombre, 120, 10)
        )
    if tipo in ("decision", "paralelo"):
        rombo = f"{c.cx},{c.y} {c.right},{c.cy} {c.cx},{c.bottom} {c.x},{c.cy}"
        marca = "×" if tipo == "decision" else "+"
        return (
            f'<polygon points="{rombo}" fill="{FONDO}" stroke="{TINTA}" stroke-width="1.5"/>'
            f'<text x="{c.cx}" y="{c.cy + 8}" font-size="24" text-anchor="middle">{marca}</text>'
            + _texto(c.x + 6, c.y - 4, nombre, 170, 10, "end")  # arriba a la izquierda
        )
    return (
        f'<rect x="{c.x}" y="{c.y}" width="{c.w}" height="{c.h}" rx="9" fill="{FONDO}" '
        f'stroke="{TINTA}" stroke-width="1.5"/>' + _texto(c.cx, c.cy + 4, nombre, c.w - 10)
    )


def svg(proc: Procedimiento) -> str:
    dib = plano(proc)
    p = dib.piscina
    partes = [
        f'<rect x="{p.x}" y="{p.y}" width="{p.w}" height="{p.h}" fill="#f7f8fa" '
        f'stroke="{TINTA}" stroke-width="1.5"/>',
        f'<text transform="translate({p.x + 19},{p.cy}) rotate(-90)" font-size="13" '
        f'font-weight="600" text-anchor="middle">{escape(proc.nombre)}</text>',
    ]
    for nombre, c in dib.carriles.items():
        partes.append(
            f'<rect x="{c.x}" y="{c.y}" width="{c.w}" height="{c.h}" fill="none" '
            f'stroke="{TINTA}"/><line x1="{c.x + 30}" y1="{c.y}" x2="{c.x + 30}" '
            f'y2="{c.bottom}" stroke="{TINTA}"/>'
            f'<text transform="translate({c.x + 19},{c.cy}) rotate(-90)" font-size="10" '
            f'text-anchor="middle">{escape(nombre)}</text>'
        )
    for f, ruta in zip(proc.flujos, dib.rutas, strict=True):
        puntos = " ".join(f"{x:.0f},{y:.0f}" for x, y in ruta)
        partes.append(
            f'<polyline points="{puntos}" fill="none" stroke="{TINTA}" stroke-width="1.2" '
            'marker-end="url(#punta)"/>'
        )
        if f.nombre:
            (x1, y1), (x2, y2) = ruta[0], ruta[1]
            partes.append(
                f'<text x="{(x1 + x2) / 2 + 6:.0f}" y="{(y1 + y2) / 2 - 4:.0f}" font-size="10" '
                f'fill="#55606b">{escape(f.nombre)}</text>'
            )
    for n in proc.nodos:
        partes.append(_forma(n.tipo, dib.formas[n.id], n.nombre))
    ancho, alto = p.right + 30, p.bottom + 30
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho:.0f} {alto:.0f}" '
        f'width="{ancho:.0f}" height="{alto:.0f}" font-family="Segoe UI, Arial, sans-serif">'
        '<defs><marker id="punta" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" '
        f'markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{TINTA}"/></marker>'
        f'</defs><rect width="100%" height="100%" fill="{FONDO}"/>{"".join(partes)}</svg>'
    )
