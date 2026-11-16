"""Genera los documentos de muestra de la prueba de extracción.

Todo el contenido es ficticio (un proyecto inventado), así que las muestras se pueden subir al
repositorio. Cada muestra tiene unas frases conocidas que se guardan en `muestras/esperado.json`:
`extraer.py` comprueba después cuántas aparecen en lo que saca Docling, para medir de forma
automática si el texto sale entero. Se ejecuta dentro del contenedor `prueba` (necesita
LibreOffice para los formatos antiguos).
"""

import json
import subprocess
import zipfile
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.util import Inches, Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

MUESTRAS = Path("muestras")
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Contenido común: un proyecto ficticio con acentos, eñes y símbolos para probar caracteres.
PROYECTO = "Proyecto Ficticio Alfa"
RESUMEN = ("La migración de los servidores del año 2027 se hará en tres fases y costará "
           "48.500 € según la estimación de configuración inicial.")
TABLA = [["Fase", "Responsable", "Duración"],
         ["Análisis", "Equipo Norte", "4 semanas"],
         ["Migración", "Equipo Sur", "6 semanas"],
         ["Validación", "Equipo Este", "2 semanas"]]
RIESGOS = "El riesgo principal es la caída del servicio de facturación durante la ventana nocturna."


def pdf_texto(ruta: Path, bordes: bool = False) -> list[str]:
    """Con `bordes=False` la tabla no tiene líneas: el caso difícil para detectar tablas."""
    estilos = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(ruta), pagesize=A4)
    doc.build([
        Paragraph(PROYECTO, estilos["Title"]),
        Paragraph("1. Resumen", estilos["Heading1"]),
        Paragraph(RESUMEN, estilos["Normal"]),
        Paragraph("2. Planificación", estilos["Heading1"]),
        Table(TABLA, style=TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]) if bordes else None),
        PageBreak(),
        Paragraph("3. Riesgos", estilos["Heading1"]),
        Paragraph(RIESGOS, estilos["Normal"]),
    ])
    return [PROYECTO, RESUMEN, RIESGOS, "Equipo Sur", "6 semanas"]


def imagen_escaneada(ruta_png: Path, ruta_pdf: Path) -> list[str]:
    """Texto pintado en una imagen: solo se puede leer con OCR."""
    lineas = ["Acta de reunión del Proyecto Ficticio Alfa",
              "Fecha: 3 de marzo de 2027",
              "Se aprueba el presupuesto de 48.500 euros.",
              "Próxima revisión: después de la fase de migración."]
    img = Image.new("RGB", (1654, 2339), "white")  # A4 a 200 ppp
    dibujo = ImageDraw.Draw(img)
    fuente = ImageFont.truetype(FUENTE, 44)
    for i, linea in enumerate(lineas):
        dibujo.text((150, 200 + i * 90), linea, fill="black", font=fuente)
    img.save(ruta_png)
    img.save(ruta_pdf, resolution=200)
    return lineas


def docx(ruta: Path) -> list[str]:
    doc = Document()
    doc.add_heading(PROYECTO, level=0)
    doc.add_heading("Resumen", level=1)
    doc.add_paragraph(RESUMEN)
    doc.add_heading("Planificación", level=1)
    tabla = doc.add_table(rows=len(TABLA), cols=3)
    for fila, valores in zip(tabla.rows, TABLA):
        for celda, valor in zip(fila.cells, valores):
            celda.text = valor
    doc.add_heading("Riesgos", level=1)
    doc.add_paragraph(RIESGOS)
    doc.save(ruta)
    return [PROYECTO, RESUMEN, RIESGOS, "Equipo Norte", "4 semanas"]


def pptx(ruta: Path) -> list[str]:
    prs = Presentation()
    portada = prs.slides.add_slide(prs.slide_layouts[0])
    portada.shapes.title.text = PROYECTO
    portada.placeholders[1].text = "Presentación de arranque"

    puntos = prs.slides.add_slide(prs.slide_layouts[1])
    puntos.shapes.title.text = "Objetivos"
    cuerpo = puntos.placeholders[1].text_frame
    cuerpo.text = "Reducir el consumo eléctrico un 30 %"
    cuerpo.add_paragraph().text = "Unificar la monitorización en un único panel"

    tabla = prs.slides.add_slide(prs.slide_layouts[5])
    tabla.shapes.title.text = "Planificación"
    t = tabla.shapes.add_table(len(TABLA), 3, Inches(1), Inches(2), Inches(8), Inches(2)).table
    for i, fila in enumerate(TABLA):
        for j, valor in enumerate(fila):
            t.cell(i, j).text = valor

    # Diagrama hecho con formas sueltas: el caso típico de un esquema en PowerPoint.
    diagrama = prs.slides.add_slide(prs.slide_layouts[5])
    diagrama.shapes.title.text = "Arquitectura"
    for i, nombre in enumerate(["Balanceador", "Servidor web", "Base de datos"]):
        caja = diagrama.shapes.add_shape(1, Inches(0.5 + i * 3.2), Inches(3), Inches(2.6), Inches(1))
        caja.text_frame.text = nombre
        caja.text_frame.paragraphs[0].runs[0].font.size = Pt(16)
    prs.save(ruta)
    return [PROYECTO, "Reducir el consumo eléctrico un 30 %",
            "Unificar la monitorización en un único panel", "Equipo Este", "Balanceador",
            "Base de datos"]


def xlsx(ruta: Path) -> list[str]:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Presupuesto"
    for fila in [["Concepto", "Importe (€)"], ["Licencias", 12000], ["Hardware", 30500],
                 ["Formación", 6000]]:
        hoja.append(fila)
    libro.save(ruta)
    return ["Licencias", "30500", "Formación"]


def vsdx(ruta: Path) -> list[str]:
    """Visio mínimo escrito a mano (OOXML): 3 formas con texto y 2 conectores.

    No hay librería libre que cree .vsdx desde cero, así que se escribe el XML justo para que
    lo abran `vsdx` y LibreOffice.
    """
    ns = 'xmlns="http://schemas.microsoft.com/office/visio/2012/main" ' \
         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

    def forma(id_, x, texto):
        return (f'<Shape ID="{id_}" Type="Shape"><Cell N="PinX" V="{x}"/><Cell N="PinY" V="4"/>'
                f'<Cell N="Width" V="1.8"/><Cell N="Height" V="0.8"/>'
                f'<Cell N="LocPinX" V="0.9"/><Cell N="LocPinY" V="0.4"/>'
                f'<Section N="Geometry" IX="0"><Row T="MoveTo" IX="1"><Cell N="X" V="0"/>'
                f'<Cell N="Y" V="0"/></Row><Row T="LineTo" IX="2"><Cell N="X" V="1.8"/>'
                f'<Cell N="Y" V="0"/></Row><Row T="LineTo" IX="3"><Cell N="X" V="1.8"/>'
                f'<Cell N="Y" V="0.8"/></Row><Row T="LineTo" IX="4"><Cell N="X" V="0"/>'
                f'<Cell N="Y" V="0.8"/></Row><Row T="LineTo" IX="5"><Cell N="X" V="0"/>'
                f'<Cell N="Y" V="0"/></Row></Section><Text>{texto}</Text></Shape>')

    def conector(id_, x1, x2):
        return (f'<Shape ID="{id_}" Type="Shape"><Cell N="BeginX" V="{x1}"/><Cell N="BeginY" V="4"/>'
                f'<Cell N="EndX" V="{x2}"/><Cell N="EndY" V="4"/>'
                f'<Section N="Geometry" IX="0"><Row T="MoveTo" IX="1"><Cell N="X" V="0"/>'
                f'<Cell N="Y" V="0"/></Row><Row T="LineTo" IX="2"><Cell N="X" V="{x2 - x1}"/>'
                f'<Cell N="Y" V="0"/></Row></Section></Shape>')

    pagina = (f'<?xml version="1.0" encoding="UTF-8"?><PageContents {ns}><Shapes>'
              + forma(1, 1.5, "Usuarios") + forma(2, 4.5, "Portal de facturación")
              + forma(3, 7.5, "Base de datos de clientes")
              + conector(4, 2.4, 3.6) + conector(5, 5.4, 6.6)
              + '</Shapes><Connects>'
              '<Connect FromSheet="4" FromCell="BeginX" ToSheet="1" ToCell="PinX"/>'
              '<Connect FromSheet="4" FromCell="EndX" ToSheet="2" ToCell="PinX"/>'
              '<Connect FromSheet="5" FromCell="BeginX" ToSheet="2" ToCell="PinX"/>'
              '<Connect FromSheet="5" FromCell="EndX" ToSheet="3" ToCell="PinX"/>'
              '</Connects></PageContents>')
    rel = "http://schemas.microsoft.com/visio/2010/relationships"
    partes = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>'
            '<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>'
            '<Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/></Types>',
        "_rels/.rels":
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rel}/document" Target="visio/document.xml"/></Relationships>',
        "visio/document.xml":
            f'<?xml version="1.0" encoding="UTF-8"?><VisioDocument {ns}/>',
        "visio/_rels/document.xml.rels":
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rel}/pages" Target="pages/pages.xml"/></Relationships>',
        "visio/pages/pages.xml":
            f'<?xml version="1.0" encoding="UTF-8"?><Pages {ns}><Page ID="0" Name="Arquitectura">'
            '<PageSheet><Cell N="PageWidth" V="9"/><Cell N="PageHeight" V="6"/></PageSheet>'
            '<Rel r:id="rId1"/></Page></Pages>',
        "visio/pages/_rels/pages.xml.rels":
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rel}/page" Target="page1.xml"/></Relationships>',
        "visio/pages/page1.xml": pagina,
    }
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, xml in partes.items():
            z.writestr(nombre, xml)
    return ["Usuarios", "Portal de facturación", "Base de datos de clientes"]


def antiguo(origen: Path, formato: str) -> Path:
    """Convierte con LibreOffice a .doc/.ppt (formatos binarios antiguos de Office)."""
    subprocess.run(["soffice", "--headless", "--convert-to", formato, "--outdir", str(MUESTRAS),
                    str(origen)], check=True, capture_output=True)
    return origen.with_suffix(f".{formato}")


def main() -> None:
    MUESTRAS.mkdir(exist_ok=True)
    esperado = {
        "informe.pdf": pdf_texto(MUESTRAS / "informe.pdf"),
        "informe_con_bordes.pdf": pdf_texto(MUESTRAS / "informe_con_bordes.pdf", bordes=True),
        "acta_escaneada.pdf": imagen_escaneada(MUESTRAS / "acta_escaneada.png",
                                               MUESTRAS / "acta_escaneada.pdf"),
        "memoria.docx": docx(MUESTRAS / "memoria.docx"),
        "presentacion.pptx": pptx(MUESTRAS / "presentacion.pptx"),
        "presupuesto.xlsx": xlsx(MUESTRAS / "presupuesto.xlsx"),
        "arquitectura.vsdx": vsdx(MUESTRAS / "arquitectura.vsdx"),
    }
    esperado["acta_escaneada.png"] = esperado["acta_escaneada.pdf"]
    esperado[antiguo(MUESTRAS / "memoria.docx", "doc").name] = esperado["memoria.docx"]
    esperado[antiguo(MUESTRAS / "presentacion.pptx", "ppt").name] = esperado["presentacion.pptx"]
    (MUESTRAS / "esperado.json").write_text(
        json.dumps(esperado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(esperado)} muestras en {MUESTRAS}/")


if __name__ == "__main__":
    main()
