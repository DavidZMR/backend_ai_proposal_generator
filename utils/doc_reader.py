"""
doc_reader.py — Extracción de texto de archivos PDF, DOCX, TXT y JSON.

Utilidad para leer documentos de entrada del usuario (briefs, propuestas
históricas, minutas escritas) y convertirlos a texto plano para que el
agente pueda procesarlos.
"""

import os
import json
import logging

logger = logging.getLogger(__name__)


def extract_text_from_file(file_path: str) -> str:
    """
    Extrae texto de un archivo según su extensión.

    Formatos soportados:
        .pdf  → pdfplumber (texto por páginas)
        .docx → python-docx (párrafos + tablas)
        .doc  → python-docx (best-effort)
        .txt  → lectura directa
        .json → lectura estructurada (propuestas históricas)

    Args:
        file_path: Ruta absoluta o relativa al archivo.

    Returns:
        Texto extraído como string limpio.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si el formato no es soportado.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return _read_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return _read_docx(file_path)
    elif ext == ".txt":
        return _read_txt(file_path)
    elif ext == ".json":
        return _read_json(file_path)
    else:
        raise ValueError(
            f"Formato no soportado: {ext}. "
            "Use .pdf, .docx, .txt o .json"
        )


def _read_pdf(path: str) -> str:
    """
    Extrae texto de un archivo PDF usando pdfplumber.
    Retorna el texto con indicadores de página.
    """
    import pdfplumber

    text_parts = []
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"[Página {i + 1}]\n{page_text}")

        if not text_parts:
            logger.warning(f"No se pudo extraer texto del PDF: {path}")
            return "[PDF sin texto extraíble]"

        return "\n\n".join(text_parts)

    except Exception as e:
        logger.error(f"Error al leer PDF {path}: {e}")
        raise RuntimeError(f"Error al leer PDF: {e}")


def _read_docx(path: str) -> str:
    """
    Extrae texto de un archivo DOCX usando python-docx.
    Incluye párrafos y contenido de tablas.
    """
    from docx import Document

    try:
        doc = Document(path)
        parts = []

        # Extraer párrafos
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if text:
                # Preservar jerarquía de headings
                if paragraph.style and paragraph.style.name.startswith("Heading"):
                    level = paragraph.style.name.replace("Heading ", "")
                    parts.append(f"\n{'#' * int(level) if level.isdigit() else '##'} {text}")
                else:
                    parts.append(text)

        # Extraer tablas
        for table in doc.tables:
            table_rows = []
            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    table_rows.append(row_text)
            if table_rows:
                parts.append("\n[Tabla]\n" + "\n".join(table_rows))

        if not parts:
            logger.warning(f"No se pudo extraer texto del DOCX: {path}")
            return "[DOCX sin contenido de texto]"

        return "\n".join(parts)

    except Exception as e:
        logger.error(f"Error al leer DOCX {path}: {e}")
        raise RuntimeError(f"Error al leer DOCX: {e}")


def _read_txt(path: str) -> str:
    """Lee un archivo de texto plano con detección de encoding."""
    encodings = ["utf-8", "latin-1", "cp1252"]

    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            return content
        except UnicodeDecodeError:
            continue

    raise RuntimeError(f"No se pudo decodificar el archivo: {path}")


def _read_json(path: str) -> str:
    """
    Lee un archivo JSON de propuesta histórica y lo convierte a texto
    estructurado legible para el agente.

    Espera un JSON con estructura:
    {
        "metadata": { "cliente": "...", "monto": "...", ... },
        "secciones": {
            "resumen_ejecutivo": "...",
            "alcance_funcional": "...",
            ...
        }
    }
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido en {path}: {e}")
        raise RuntimeError(f"Error al parsear JSON: {e}")

    parts = []

    # Metadata
    if "metadata" in data:
        meta = data["metadata"]
        parts.append("=== DATOS DE LA PROPUESTA ===")
        for key, value in meta.items():
            label = key.replace("_", " ").title()
            parts.append(f"{label}: {value}")
        parts.append("")

    # Secciones
    if "secciones" in data:
        for section_name, content in data["secciones"].items():
            header = section_name.replace("_", " ").title()
            parts.append(f"=== {header.upper()} ===")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            parts.append(f"  {k}: {v}")
                        parts.append("")
                    else:
                        parts.append(f"  • {item}")
            elif isinstance(content, dict):
                for k, v in content.items():
                    parts.append(f"  {k}: {v}")
            parts.append("")

    if not parts:
        # Fallback: convertir todo el JSON a texto
        return json.dumps(data, indent=2, ensure_ascii=False)

    return "\n".join(parts)
