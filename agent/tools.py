"""
tools.py — Herramientas que el agente Claude puede utilizar (tool_use).

Define los esquemas JSON para la API de Anthropic y las funciones de Python
que ejecutan la lógica real.
"""

import os
import json
import logging
from typing import Dict, Any, List

from utils.doc_reader import extract_text_from_file
from utils.transcription import transcribe_audio as utils_transcribe
from utils.rag_setup import search_similar
from utils.docx_builder import build_docx
from utils.pdf_converter import convert_sections_to_pdf

logger = logging.getLogger(__name__)

# ==========================================
# 1. ESQUEMAS DE HERRAMIENTAS (Anthropic API)
# ==========================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "extract_document_text",
            "description": "Extrae todo el texto de un documento proporcionado por el usuario (PDF, DOCX, TXT). Úsalo para leer el brief o requerimientos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Ruta absoluta o relativa al archivo a leer."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "transcribe_audio",
            "description": "Transcribe un archivo de audio (mp3, wav, mp4) a texto. Úsalo cuando el usuario proporciona un audio con la minuta o requerimientos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "audio_path": {
                        "type": "string",
                        "description": "Ruta absoluta o relativa al archivo de audio."
                    }
                },
                "required": ["audio_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_proposal_examples",
            "description": "Busca en la base de datos de conocimiento propuestas comerciales históricas similares para usarlas como referencia de estilo, formato o montos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Tema o palabras clave de búsqueda (ej. 'app móvil', 'ecommerce inmobiliario')."
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_template_section",
            "description": "Obtiene las instrucciones y guías específicas de cómo debe redactarse una sección particular de la propuesta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_name": {
                        "type": "string",
                        "description": "Nombre de la sección (ej. 'resumen_ejecutivo', 'alcance_funcional', 'arquitectura', 'plan_sprints', 'supuestos', 'exclusiones', 'inversion')."
                    }
                },
                "required": ["section_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_section_content",
            "description": "Envía el contenido final generado para una sección específica. DEBES usar esta herramienta para guardar tu progreso de redacción.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_name": {
                        "type": "string",
                        "description": "El nombre de la sección que estás entregando."
                    },
                    "content": {
                        "type": "string",
                        "description": "El texto completo redactado y formateado para esta sección."
                    }
                },
                "required": ["section_name", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_metadata",
            "description": "Guarda los metadatos estimados del proyecto (monto, duración, tipo). DEBES llamar a esta herramienta al inicio para registrar estas estimaciones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "string",
                        "description": "Monto estimado en formato de texto (ej. '$250,000 MXN', 'Por definir')."
                    },
                    "duration": {
                        "type": "string",
                        "description": "Duración estimada (ej. '3 meses', '2 semanas')."
                    },
                    "project_type": {
                        "type": "string",
                        "description": "Tipo de proyecto (ej. 'App Móvil', 'E-commerce', 'Desarrollo a Medida')."
                    },
                    "solution_type": {
                        "type": "string",
                        "description": "Clasificación explícita de la solución propuesta (ej. 'App Móvil', 'Página Web', 'E-commerce', 'CRM', 'Plataforma SaaS', 'API/Backend', 'Sistema ERP', 'Otro')."
                    },
                    "tech_stack": {
                        "type": "string",
                        "description": "Stack tecnológico principal propuesto para el proyecto (ej. 'React Native, Node.js, PostgreSQL')."
                    }
                },
                "required": ["amount", "duration", "project_type", "solution_type", "tech_stack"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "assemble_and_export",
            "description": "Ensambla todas las secciones generadas y exporta la propuesta a formatos DOCX y PDF. Llama a esta herramienta SOLO cuando hayas terminado todas las secciones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prospect_name": {
                        "type": "string",
                        "description": "Nombre del cliente o prospecto."
                    }
                },
                "required": ["prospect_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_budget",
            "description": "Calcula de forma matemáticamente exacta el presupuesto de un proyecto basado en las horas estimadas de los perfiles tecnológicos necesarios. Llama a esta herramienta cuando redactes la sección 'inversion'. NO inventes precios por tu cuenta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours_frontend": { "type": "string", "description": "Horas estimadas de desarrollo Frontend. (ej. '120')" },
                    "hours_backend": { "type": "string", "description": "Horas estimadas de desarrollo Backend. (ej. '80')" },
                    "hours_design": { "type": "string", "description": "Horas estimadas de Diseño UI/UX. (ej. '40')" },
                    "hours_pm": { "type": "string", "description": "Horas estimadas de Project Management. (ej. '20')" },
                    "hours_qa": { "type": "string", "description": "Horas estimadas de QA / Testing. (ej. '40')" },
                    "total_weeks": { "type": "string", "description": "Suma total de la duración en semanas de todos los sprints planificados en 'plan_sprints'." }
                },
                "required": ["hours_frontend", "hours_backend", "hours_design", "hours_pm", "hours_qa", "total_weeks"]
            }
        }
    }
]


# ==========================================
# 2. FUNCIONES DE EJECUCIÓN (Wrappers)
# ==========================================

def tool_extract_document_text(file_path: str) -> str:
    try:
        doc_text = extract_text_from_file(file_path)
        # TRUNCATE to avoid hitting Groq's 15k TPM limit when 4+ docs are uploaded
        if len(doc_text) > 4500:
            doc_text = doc_text[:4500] + "\n...[RESTO DEL DOCUMENTO TRUNCADO POR LÍMITE DE TOKENS. INFIERE EL RESTO.]"
        return doc_text
    except Exception as e:
        return f"Error al leer el documento: {e}"

def tool_transcribe_audio(audio_path: str) -> str:
    try:
        return utils_transcribe(audio_path)
    except Exception as e:
        return f"Error al transcribir el audio: {e}"

def tool_search_proposal_examples(topic: str, num_results: int = 1) -> str:
    try:
        results = search_similar(topic, n_results=num_results)
        if not results:
            return "No se encontraron propuestas históricas similares."
        
        output = []
        for i, res in enumerate(results):
            meta = res.get("metadata", {})
            cliente = meta.get("cliente", "Desconocido")
            doc = res.get("document", "")
            # TRUNCATE to avoid hitting Groq's 6000 TPM limit
            if len(doc) > 4500:
                doc = doc[:4500] + "\n...[TRUNCADO POR LÍMITE DE TOKENS]"
            output.append(f"--- EJEMPLO {i+1}: Cliente {cliente} ---\n{doc}\n")
            
        return "\n".join(output)
    except Exception as e:
        return f"Error al buscar ejemplos: {e}"

def tool_get_template_section(section_name: str) -> str:
    try:
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
            "storage", "templates", "section_guides.json"
        )
        if not os.path.exists(template_path):
            return "El archivo de plantillas no existe."
            
        with open(template_path, "r", encoding="utf-8") as f:
            guides = json.load(f)
            
        return guides.get(section_name, f"No hay guía específica para la sección: {section_name}")
    except Exception as e:
        return f"Error al leer la plantilla: {e}"

def tool_submit_section_content(section_name: str, content: str) -> str:
    """
    Mock function. El orquestador interceptará esta llamada para guardar 
    el progreso en la base de datos (Supabase) sin necesidad de que la tool 
    haga nada aquí. Solo retornamos un ACK para que Claude sepa que se guardó.
    """
    return f"Contenido de la sección '{section_name}' guardado exitosamente."

def tool_save_metadata(amount: str, duration: str, project_type: str, solution_type: str = None, tech_stack: str = None) -> str:
    """
    Mock function interceptada por el orquestador.
    """
    return "Metadatos guardados exitosamente."

def tool_assemble_and_export(sections: dict, prospect_name: str, output_dir: str) -> str:
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # Limpiar prospect_name para archivo
        safe_name = "".join([c for c in prospect_name if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        safe_name = safe_name.replace(" ", "_").lower()
        if not safe_name:
            safe_name = "propuesta"
            
        docx_path = os.path.join(output_dir, f"propuesta_{safe_name}.docx")
        pdf_path = os.path.join(output_dir, f"propuesta_{safe_name}.pdf")
        
        build_docx(sections, prospect_name, docx_path)
        convert_sections_to_pdf(sections, prospect_name, pdf_path)
        
        return json.dumps({
            "status": "success",
            "message": "Archivos ensamblados y exportados exitosamente.",
            "docx_path": docx_path,
            "pdf_path": pdf_path
        })
    except Exception as e:
        return f"Error al ensamblar/exportar: {e}"

def tool_calculate_budget(hours_frontend, hours_backend, hours_design, hours_pm, hours_qa, total_weeks=None, proposal_id=None) -> str:
    """Calcula el presupuesto leyendo las tarifas base desde Supabase y retorna un markdown."""
    try:
        hours_frontend = int(hours_frontend)
        hours_backend = int(hours_backend)
        hours_design = int(hours_design)
        hours_pm = int(hours_pm)
        hours_qa = int(hours_qa)
        if total_weeks is not None:
            total_weeks = int(total_weeks)
        from utils.supabase_client import get_supabase_client
        db = get_supabase_client()
        res = db.table("settings").select("value").eq("key", "pricing_rates").execute()
        rates = {"frontend": 600, "backend": 700, "design": 500, "pm": 600, "qa": 400}
        if res.data:
            rates = res.data[0]["value"]
            
        cost_fe = hours_frontend * rates.get("frontend", 600)
        cost_be = hours_backend * rates.get("backend", 700)
        cost_ux = hours_design * rates.get("design", 500)
        cost_pm = hours_pm * rates.get("pm", 600)
        cost_qa = hours_qa * rates.get("qa", 400)
        
        subtotal = cost_fe + cost_be + cost_ux + cost_pm + cost_qa
        iva = subtotal * 0.16
        total = subtotal + iva
        
        if proposal_id:
            update_data = {"amount": f"${total:,.2f} MXN"}
            if total_weeks:
                update_data["duration"] = f"{total_weeks} semanas"
            db.table("proposals").update(update_data).eq("id", proposal_id).execute()
        
        table = "| Perfil / Actividad | Horas | Tarifa/Hr (MXN) | Costo (MXN) |\n"
        table += "|---|---|---|---|\n"
        if hours_frontend > 0: table += f"| Desarrollo Frontend | {hours_frontend} | ${rates.get('frontend', 600)} | ${cost_fe:,.2f} |\n"
        if hours_backend > 0: table += f"| Desarrollo Backend | {hours_backend} | ${rates.get('backend', 700)} | ${cost_be:,.2f} |\n"
        if hours_design > 0: table += f"| Diseño UI/UX | {hours_design} | ${rates.get('design', 500)} | ${cost_ux:,.2f} |\n"
        if hours_pm > 0: table += f"| Project Management | {hours_pm} | ${rates.get('pm', 600)} | ${cost_pm:,.2f} |\n"
        if hours_qa > 0: table += f"| QA / Pruebas | {hours_qa} | ${rates.get('qa', 400)} | ${cost_qa:,.2f} |\n"
        
        table += "\n"
        table += f"**Subtotal:** ${subtotal:,.2f} MXN\n\n"
        table += f"**IVA (16%):** ${iva:,.2f} MXN\n\n"
        table += f"**Inversión Total:** ${total:,.2f} MXN\n\n"
        table += "*Nota: Estimación basada en esfuerzo nominal de Sprints planificados.*"
        
        return table
    except Exception as e:
        return f"Error calculando presupuesto: {e}"

# ==========================================
# 3. DISPATCHER
# ==========================================

TOOL_MAP = {
    "extract_document_text": tool_extract_document_text,
    "transcribe_audio": tool_transcribe_audio,
    "search_proposal_examples": tool_search_proposal_examples,
    "get_template_section": tool_get_template_section,
    "save_metadata": tool_save_metadata,
    "submit_section_content": tool_submit_section_content,
    "assemble_and_export": tool_assemble_and_export,
    "calculate_budget": tool_calculate_budget
}

def execute_tool(tool_name: str, tool_args: dict) -> Any:
    """Ejecuta una herramienta y retorna su resultado."""
    if tool_name not in TOOL_MAP:
        return f"Herramienta desconocida: {tool_name}"
        
    func = TOOL_MAP[tool_name]
    logger.info(f"Ejecutando tool: {tool_name} con args: {tool_args}")
    
    try:
        return func(**tool_args)
    except Exception as e:
        logger.error(f"Error ejecutando tool {tool_name}: {e}")
        return f"Error interno en herramienta {tool_name}: {e}"
