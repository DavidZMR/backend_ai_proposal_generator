"""
pdf_converter.py — Generación de documentos PDF por código con ReportLab.

Crea PDFs profesionales con formato LinkThinks de forma nativa sin
depender de Microsoft Word o LibreOffice.
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.pdfgen import canvas

# Colores LinkThinks
NAVY_COLOR = colors.HexColor("#0B1E3A")
TEAL_COLOR = colors.HexColor("#16B5A0")

def _header_footer(canvas_obj: canvas.Canvas, doc: SimpleDocTemplate):
    """Agrega pie de página corporativo en cada página del PDF."""
    canvas_obj.saveState()
    
    # Pie de página
    canvas_obj.setFont('Helvetica', 9)
    canvas_obj.setFillColor(colors.gray)
    canvas_obj.drawString(72, 40, "Confidencial — Propuesta de Servicios LinkThinks")
    
    # Número de página a la derecha
    page_num = canvas_obj.getPageNumber()
    canvas_obj.drawRightString(letter[0] - 72, 40, f"Página {page_num}")
    
    canvas_obj.restoreState()

def convert_sections_to_pdf(sections: dict, prospect_name: str, output_path: str) -> str:
    """
    Genera un archivo PDF directamente desde las secciones de la propuesta.
    
    Args:
        sections: Diccionario con el contenido de las secciones.
        prospect_name: Nombre del cliente/prospecto.
        output_path: Ruta donde se guardará el archivo PDF.
        
    Returns:
        Ruta del archivo PDF generado.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    styles = getSampleStyleSheet()
    
    # Estilos corporativos
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=32,
        textColor=NAVY_COLOR,
        spaceAfter=20,
        alignment=1 # Centro
    )
    
    subtitle_style = ParagraphStyle(
        'SubtitleStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=16,
        textColor=colors.dimgray,
        spaceAfter=12,
        alignment=1
    )
    
    heading_style = ParagraphStyle(
        'HeadingStyle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=TEAL_COLOR,
        spaceBefore=24,
        spaceAfter=12
    )
    
    subheading_style = ParagraphStyle(
        'SubheadingStyle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=NAVY_COLOR,
        spaceBefore=12,
        spaceAfter=6
    )
    
    normal_style = styles['Normal']
    normal_style.fontSize = 11
    normal_style.leading = 16
    normal_style.textColor = colors.black
    
    bullet_style = ParagraphStyle(
        'BulletStyle',
        parent=normal_style,
        leftIndent=20,
        spaceBefore=3,
        spaceAfter=3
    )
    
    story = []
    
    # 1. Portada
    story.append(Spacer(1, 200)) # Centrar verticalmente
    story.append(Paragraph("Propuesta de Servicios", title_style))
    story.append(Paragraph(f"Para: {prospect_name}", subtitle_style))
    story.append(PageBreak())
    
    # 2. Secciones
    order = [
        ("Resumen Ejecutivo", "resumen_ejecutivo"),
        ("Alcance Funcional", "alcance_funcional"),
        ("Arquitectura Propuesta", "arquitectura"),
        ("Plan de Sprints", "plan_sprints"),
        ("Supuestos", "supuestos"),
        ("Exclusiones", "exclusiones"),
        ("Inversión", "inversion"),
    ]
    
    for title_text, key in order:
        if key in sections and sections[key]:
            story.append(Paragraph(title_text, heading_style))
            
            content = sections[key]
            
            table_data = []
            
            def flush_table():
                if table_data:
                    # Ancho sugerido: distribuimos el ancho de la página entre las columnas
                    avail_width = letter[0] - 144 # 72 left + 72 right margin
                    col_widths = [avail_width / max(1, len(table_data[0]))] * max(1, len(table_data[0]))
                    
                    t = Table(table_data, colWidths=col_widths)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F9FAFB")),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#374151")),
                        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0,0), (-1,0), 10),
                        ('TOPPADDING', (0,0), (-1,0), 10),
                        ('BACKGROUND', (0,1), (-1,-1), colors.white),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ]))
                    story.append(t)
                    story.append(Spacer(1, 12))
                    table_data.clear()

            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    flush_table()
                    continue
                
                # Escapar caracteres HTML reservados por ReportLab
                line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                
                if line.startswith("|") and line.endswith("|"):
                    cells = [c.strip() for c in line.strip('|').split('|')]
                    if all(c.replace("-", "").strip() == "" for c in cells):
                        continue
                        
                    # Para la fila de encabezado (primera de table_data), usaremos una fuente normal_style ligeramente modificada no es necesaria si TableStyle ya aplica Bold,
                    # pero envolver en Paragraph permite que el texto haga salto de línea si es muy largo.
                    row_elements = [Paragraph(c, normal_style) for c in cells]
                    table_data.append(row_elements)
                else:
                    flush_table()
                    if line.startswith("- ") or line.startswith("* "):
                        story.append(Paragraph(f"• {line[2:].strip()}", bullet_style))
                    elif line.startswith("## "):
                        story.append(Paragraph(line[3:].strip(), subheading_style))
                    elif line.startswith("# "):
                        story.append(Paragraph(line[2:].strip(), subheading_style))
                    else:
                        story.append(Paragraph(line, normal_style))
            
            flush_table()
                    
            story.append(Spacer(1, 14))
            # Opcional: Separar secciones grandes por página
            if key in ["alcance_funcional", "plan_sprints", "inversion"]:
                story.append(PageBreak())
                
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    
    return output_path
