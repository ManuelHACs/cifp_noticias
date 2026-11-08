#!/usr/bin/env python3
"""Actualiza el noticiario del CIFP La Granja.

Lee búsquedas de Google Noticias y feeds RSS definidos en config.json,
filtra y clasifica las noticias por área y ámbito, y genera:
  - news.json  -> lo lee index.html
  - feed.xml   -> RSS para suscribirse al noticiario

Solo usa la biblioteca estándar de Python (no hay que instalar nada).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config.json"
SALIDA_JSON = RAIZ / "news.json"
SALIDA_RSS = RAIZ / "feed.xml"

AGENTE = "Mozilla/5.0 (compatible; NoticiarioCIFPLaGranja/1.0; +https://github.com/ManuelHACs/cifp_noticias)"
AHORA = datetime.now(timezone.utc)
MEDIA_NS = "{http://search.yahoo.com/mrss/}"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


# ---------------------------------------------------------------- utilidades

def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples (para comparar)."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " " + re.sub(r"\s+", " ", texto.lower()).strip() + " "


def patron(palabra: str) -> re.Pattern:
    """Palabra clave -> regex. Empieza en límite de palabra; si la palabra
    lleva espacio al principio o al final, también debe terminar en límite."""
    exacta = palabra != palabra.strip()
    p = re.escape(normalizar(palabra).strip())
    return re.compile(r"\b" + p + (r"\b" if exacta else ""))


def limpiar_html(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def recortar(texto: str, n: int = 260) -> str:
    if len(texto) <= n:
        return texto
    corte = texto[:n].rsplit(" ", 1)[0]
    return corte.rstrip(",.;:") + "…"


def fecha(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        d = parsedate_to_datetime(texto)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def descargar(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def clave_titulo(titulo: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", "", normalizar(titulo)).strip()
    return hashlib.sha1(t[:90].encode()).hexdigest()[:16]


# ------------------------------------------------------------------ lectura

def leer_items(xml: bytes) -> list[dict]:
    """Devuelve los items de un RSS 2.0 o Atom como diccionarios simples."""
    raiz = ET.fromstring(xml)
    items = []
    for it in raiz.iter("item"):
        imagen = None
        for tag in (MEDIA_NS + "content", MEDIA_NS + "thumbnail", "enclosure"):
            el = it.find(tag)
            if el is not None and el.get("url") and (tag != "enclosure" or (el.get("type") or "").startswith("image")):
                imagen = el.get("url")
                break
        fuente = it.find("source")
        items.append({
            "titulo": (it.findtext("title") or "").strip(),
            "enlace": (it.findtext("link") or "").strip(),
            "resumen": it.findtext("description") or "",
            "fecha": it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date"),
            "fuente": fuente.text.strip() if fuente is not None and fuente.text else None,
            "imagen": imagen,
        })
    for it in raiz.iter(ATOM_NS + "entry"):
        enlace = it.find(ATOM_NS + "link")
        items.append({
            "titulo": (it.findtext(ATOM_NS + "title") or "").strip(),
            "enlace": enlace.get("href") if enlace is not None else "",
            "resumen": it.findtext(ATOM_NS + "summary") or it.findtext(ATOM_NS + "content") or "",
            "fecha": it.findtext(ATOM_NS + "published") or it.findtext(ATOM_NS + "updated"),
            "fuente": None,
            "imagen": None,
        })
    return items


def url_google_news(q: str, dias: int) -> str:
    consulta = f"{q} when:{dias}d"
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": consulta, "hl": "es", "gl": "ES", "ceid": "ES:es"})


# ------------------------------------------------------------ clasificación

class Clasificador:
    def __init__(self, cfg: dict):
        self.areas = {k: [patron(p) for p in v["palabras"]] for k, v in cfg["areas"].items()}
        self.cifp = [patron(p) for p in cfg["palabras_cifp"]]
        self.cantabria = [patron(p) for p in cfg["palabras_cantabria"]]
        self.excluir = [patron(p) for p in cfg.get("excluir", [])]

    @staticmethod
    def _cuenta(pats, texto):
        return sum(1 for p in pats if p.search(texto))

    def excluida(self, titulo: str) -> bool:
        return self._cuenta(self.excluir, normalizar(titulo)) > 0

    def area(self, titulo: str, resumen: str, defecto: str | None) -> str | None:
        t, r = normalizar(titulo), normalizar(resumen)
        puntos = {}
        for k, pats in self.areas.items():
            # el titular pesa el doble que el resumen
            s = 2 * self._cuenta(pats, t) + self._cuenta(pats, r)
            if s:
                puntos[k] = s
        if defecto and defecto in self.areas:
            puntos[defecto] = puntos.get(defecto, 0) + 1  # pequeño empujón
        if not puntos:
            return None
        # "centro" solo gana si no hay un área técnica clara
        mejor = max(puntos, key=lambda k: (puntos[k] - (1 if k == "centro" else 0), k != "centro"))
        return mejor

    def ambito(self, titulo: str, resumen: str, defecto: str) -> str:
        texto = normalizar(titulo + " " + resumen)
        if self._cuenta(self.cifp, texto):
            return "cifp"
        if self._cuenta(self.cantabria, texto):
            return "cantabria"
        # una búsqueda "cantabria" que no menciona Cantabria en el texto visible
        # (Google filtra por el cuerpo de la noticia): se respeta su ámbito
        return defecto if defecto in ("cantabria", "nacional") else "cantabria"


# --------------------------------------------------------------- principal

def procesar(items, origen: dict, clasif: Clasificador, es_google: bool, limite: datetime) -> list[dict]:
    salida = []
    for it in items:
        titulo, fuente = it["titulo"], it["fuente"] or origen.get("fuente")
        if not titulo or not it["enlace"]:
            continue
        if es_google and fuente and titulo.endswith(" - " + fuente):
            titulo = titulo[: -len(" - " + fuente)].strip()
        elif es_google and " - " in titulo and not fuente:
            titulo, fuente = titulo.rsplit(" - ", 1)
        resumen = "" if es_google else recortar(limpiar_html(it["resumen"]))
        d = fecha(it["fecha"])
        if d is None or d < limite or d > AHORA + timedelta(days=1):
            continue
        if clasif.excluida(titulo):
            continue
        aceptar_todo = origen.get("aceptar_todo", False)
        defecto_area = origen.get("area") if (es_google or aceptar_todo) else None
        area = clasif.area(titulo, resumen, defecto_area)
        if area is None:
            continue  # feed general sin relación con nuestras áreas
        if aceptar_todo and origen.get("ambito") == "cifp":
            ambito = "cifp"  # noticias publicadas por el propio centro
        else:
            ambito = clasif.ambito(titulo, resumen, origen.get("ambito", "nacional"))
        salida.append({
            "id": clave_titulo(titulo),
            "titulo": titulo,
            "resumen": resumen,
            "fecha": d.isoformat(timespec="seconds"),
            "area": area,
            "ambito": ambito,
            "fuente": fuente or "Desconocida",
            "url": it["enlace"],
            "imagen": it["imagen"] if (it["imagen"] or "").startswith("https://") else None,
        })
    return salida


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    clasif = Clasificador(cfg)
    lim_general = AHORA - timedelta(days=cfg.get("dias_maximos", 45))
    lim_cifp = AHORA - timedelta(days=cfg.get("dias_maximos_cifp", 180))

    nuevas: list[dict] = []
    errores = 0
    origenes = [("google", b) for b in cfg.get("busquedas", [])] + [("feed", f) for f in cfg.get("feeds", [])]
    for tipo, o in origenes:
        es_google = tipo == "google"
        url = url_google_news(o["q"], o.get("dias", 14)) if es_google else o["url"]
        nombre = o["q"] if es_google else o.get("fuente", o["url"])
        try:
            items = leer_items(descargar(url))
        except Exception as e:  # una fuente caída no debe parar el resto
            errores += 1
            print(f"  ✗ {nombre[:70]}: {e}", file=sys.stderr)
            continue
        limite = lim_cifp if o.get("ambito") == "cifp" else lim_general
        ok = procesar(items, o, clasif, es_google, limite)
        print(f"  ✓ {nombre[:70]}: {len(items)} leídas, {len(ok)} válidas")
        nuevas.extend(ok)

    # combinar con lo que ya había, para no perder noticias que salen de los feeds
    anteriores = []
    if SALIDA_JSON.exists():
        try:
            anteriores = json.loads(SALIDA_JSON.read_text(encoding="utf-8")).get("noticias", [])
        except (ValueError, AttributeError):
            pass

    # si se han renombrado o quitado áreas en config.json, se reclasifican las antiguas
    for n in anteriores:
        if n.get("area") not in cfg["areas"]:
            n["area"] = clasif.area(n["titulo"], n.get("resumen", ""), "centro")

    por_id: dict[str, dict] = {}
    for n in anteriores + nuevas:  # las nuevas sobrescriben
        previa = por_id.get(n["id"])
        # si una noticia ya estaba como "cifp", se mantiene
        if previa and previa["ambito"] == "cifp":
            n["ambito"] = "cifp"
        por_id[n["id"]] = n

    def vigente(n):
        d = fecha(n["fecha"])
        return d and d >= (lim_cifp if n["ambito"] == "cifp" else lim_general)

    noticias = sorted((n for n in por_id.values() if vigente(n)), key=lambda n: n["fecha"], reverse=True)
    # las del CIFP se conservan siempre; el límite se aplica al resto
    cifp = [n for n in noticias if n["ambito"] == "cifp"]
    resto = [n for n in noticias if n["ambito"] != "cifp"][: max(0, cfg.get("max_noticias", 200) - len(cifp))]
    noticias = sorted(cifp + resto, key=lambda n: n["fecha"], reverse=True)

    if not noticias and errores == len(origenes):
        print("Todas las fuentes han fallado; no se modifica nada.", file=sys.stderr)
        return 1

    datos = {
        "actualizado": AHORA.isoformat(timespec="seconds"),
        "areas": {k: v["nombre"] for k, v in cfg["areas"].items()},
        "noticias": noticias,
    }
    SALIDA_JSON.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    escribir_rss(cfg, datos)
    print(f"Total: {len(noticias)} noticias ({len(nuevas)} recogidas en esta pasada, {errores} fuentes con error)")
    return 0


def escribir_rss(cfg: dict, datos: dict) -> None:
    base = cfg.get("url_sitio", "")
    rss = ET.Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = cfg.get("titulo", "Noticiario")
    ET.SubElement(ch, "link").text = base
    ET.SubElement(ch, "description").text = "Actualidad agraria, ganadera, forestal y agroalimentaria para el CIFP La Granja, Cantabria y España."
    ET.SubElement(ch, "language").text = "es-ES"
    ET.SubElement(ch, "lastBuildDate").text = format_datetime(AHORA)
    ET.SubElement(ch, "atom:link", {"href": base + "feed.xml", "rel": "self", "type": "application/rss+xml"})
    ambitos = {"cifp": "CIFP La Granja", "cantabria": "Cantabria", "nacional": "Nacional"}
    for n in datos["noticias"][:60]:
        it = ET.SubElement(ch, "item")
        ET.SubElement(it, "title").text = n["titulo"]
        ET.SubElement(it, "link").text = n["url"]
        ET.SubElement(it, "guid", {"isPermaLink": "false"}).text = n["id"]
        ET.SubElement(it, "pubDate").text = format_datetime(fecha(n["fecha"]))
        ET.SubElement(it, "category").text = datos["areas"].get(n["area"], n["area"])
        ET.SubElement(it, "category").text = ambitos.get(n["ambito"], n["ambito"])
        ET.SubElement(it, "source", {"url": n["url"]}).text = n["fuente"]
        ET.SubElement(it, "description").text = n["resumen"] or f"{n['fuente']} · {ambitos.get(n['ambito'])}"
    ET.indent(rss, space=" ")
    SALIDA_RSS.write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="utf-8"))


if __name__ == "__main__":
    sys.exit(main())
