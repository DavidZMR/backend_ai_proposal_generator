"""
docx_builder.py — Construcción de documentos de propuesta en formato DOCX.

Permite generar propuestas comerciales en formato Word aplicando estilos
corporativos de LinkThinks.
"""

import os
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Colores Corporativos LinkThinks
TEAL_HEX = (22, 181, 160)  # #16B5A0
NAVY_HEX = (11, 30, 58)    # #0B1E3A

def build_docx(sections: dict, prospect_name: str, output_path: str) -> str:
    """
    Genera un archivo DOCX con el contenido de la propuesta usando estilos corporativos.
    
    Args:
        sections: Diccionario con el contenido generado de las secciones.
        prospect_name: Nombre del cliente/prospecto.
        output_path: Ruta absoluta donde se guardará el archivo DOCX.
        
    Returns:
        La misma ruta del archivo generado.
    """
    doc = Document()
    
    # 1. Portada
    doc.add_picture = None # Para evitar error lint si lo llamamos luego
    
    # Espaciado superior para centrar verticalmente la portada
    for _ in range(5):
        doc.add_paragraph()
        
    title = doc.add_paragraph("Propuesta de Servicios")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.runs[0]
    title_run.font.name = 'Arial'
    title_run.font.size = Pt(32)
    title_run.font.color.rgb = RGBColor(*NAVY_HEX)
    title_run.font.bold = True
    
    doc.add_paragraph()
    
    subtitle = doc.add_paragraph(f"Para: {prospect_name}")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_run = subtitle.runs[0]
    subtitle_run.font.name = 'Arial'
    subtitle_run.font.size = Pt(16)
    subtitle_run.font.color.rgb = RGBColor(100, 100, 100)
    
    doc.add_page_break()
    
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
            # Encabezado de la sección
            h = doc.add_heading(title_text, level=1)
            h_run = h.runs[0]
            h_run.font.name = 'Arial'
            h_run.font.color.rgb = RGBColor(*TEAL_HEX)
            
            content = sections[key]
            
            # Procesamiento simple de párrafos, listas y TABLAS
            in_table = False
            current_table = None
            
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    in_table = False
                    continue
                
                if line.startswith("|") and line.endswith("|"):
                    if not in_table:
                        in_table = True
                        current_table = doc.add_table(rows=0, cols=0)
                        current_table.style = 'Table Grid'
                    
                    # Remove edge pipes and split
                    cells = [c.strip() for c in line.strip('|').split('|')]
                    
                    # Skip markdown separator line like |---|---|
                    if all(c.replace("-", "").strip() == "" for c in cells):
                        continue
                    
                    # Ensure table has enough columns
                    if len(current_table.columns) == 0:
                        for _ in cells:
                            current_table.add_column(Inches(1.2))
                            
                    row_cells = current_table.add_row().cells
                    for idx, cell_text in enumerate(cells):
                        if idx < len(row_cells):
                            row_cells[idx].text = cell_text
                else:
                    in_table = False
                    if line.startswith("- ") or line.startswith("* "):
                        p = doc.add_paragraph(line[2:].strip(), style='List Bullet')
                    elif line.startswith("#"):
                        # Soporte básico para subheadings
                        clean_line = line.lstrip("#").strip()
                        p = doc.add_heading(clean_line, level=2)
                        p.runs[0].font.color.rgb = RGBColor(*NAVY_HEX)
                    else:
                        p = doc.add_paragraph(line)
                    
            doc.add_page_break()
            
    # Crear directorio si no existe
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    doc.save(output_path)
    return output_path
