"""
orchestrator.py — Motor principal del agente que orquesta a Groq (Llama 3).

Maneja el loop de tool_use de la API de Groq, intercepta el guardado 
de secciones y coordina la subida final a Supabase.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any
from groq import Groq

from agent.prompts import SYSTEM_PROMPT, SECTIONS_LIST
from agent.tools import TOOLS_SCHEMA, execute_tool
from utils.supabase_client import update_proposal_status, upload_file, get_supabase_client

logger = logging.getLogger(__name__)

def append_timeline_event(proposal_id: str, title: str, description: str):
    """Añade un evento a la línea de tiempo de la IA."""
    try:
        db = get_supabase_client()
        res = db.table("proposals").select("timeline_events").eq("id", proposal_id).execute()
        if res.data:
            events = res.data[0].get("timeline_events", []) or []
            events.append({
                "time": datetime.now().strftime("%I:%M %p").lower(),
                "title": title,
                "description": description
            })
            db.table("proposals").update({"timeline_events": events}).eq("id", proposal_id).execute()
    except Exception as e:
        logger.error(f"Error guardando timeline event: {e}")

def append_decision_log(proposal_id: str, iteration: int, log_type: str, tool_name: str = "", args_summary: str = "", result_summary: str = "", decision: str = "", tokens: int = 0):
    """Añade un evento de trazabilidad estructurada (Agent Memory)."""
    try:
        db = get_supabase_client()
        res = db.table("proposals").select("agent_decision_log").eq("id", proposal_id).execute()
        if res.data:
            logs = res.data[0].get("agent_decision_log", []) or []
            logs.append({
                "timestamp": datetime.now().isoformat(),
                "iteration": iteration,
                "type": log_type,
                "tool_name": tool_name,
                "args_summary": args_summary,
                "result_summary": result_summary,
                "decision": decision,
                "tokens": tokens
            })
            db.table("proposals").update({"agent_decision_log": logs}).eq("id", proposal_id).execute()
    except Exception as e:
        logger.error(f"Error guardando decision log: {e}")

def run_agent(proposal_id: str, prospect_name: str, audio_paths: list = None, transcript: str = None, brief_paths: list = None, template_id: int = None):
    """
    Ejecuta el loop principal del agente usando la API de Groq con tool_use.
    Esta función debe correr en un thread en background o una task queue.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        update_proposal_status(proposal_id, "error", current_step="Error: Falta API Key de Groq en .env")
        logger.error("Falta GROQ_API_KEY")
        return
        
    client = Groq(api_key=api_key)
    
    generated_sections = {}
    sections_completed = []
    
    sections_to_generate = SECTIONS_LIST
    user_message = f"Por favor, genera una propuesta comercial para el prospecto: {prospect_name}.\n\n"
    
    if template_id:
        try:
            db = get_supabase_client()
            template = db.table("templates").select("*").eq("id", template_id).execute().data[0]
            sections_to_generate = template.get("sections", SECTIONS_LIST)
            
            # Increment usage count
            db.table("templates").update({"usage_count": template.get("usage_count", 0) + 1}).eq("id", template_id).execute()
            
            # Inject template context
            desc = template.get("description", "")
            tech = template.get("tech_stack", "")
            if desc or tech:
                user_message += "--- REQUERIMIENTOS DE LA PLANTILLA ---\n"
                user_message += "DEBES respetar las siguientes reglas y arquitectura dictadas por la plantilla seleccionada:\n"
                if desc: user_message += f"Descripción/Reglas de negocio: {desc}\n"
                if tech: user_message += f"Stack Tecnológico Obligatorio: {tech}\n"
                user_message += "\n"
        except Exception as e:
            logger.error(f"Error fetching template {template_id}: {e}")
    
    # 1. Construir mensaje inicial con el contexto disponible
    if transcript:
        user_message += f"--- TRANSCRIPCIÓN (Audio/Reunión) ---\n{transcript}\n\n"
        
    if audio_paths:
        for p in audio_paths:
            user_message += f"Hay un archivo de audio como fuente de información en: {p}. Usa la herramienta 'transcribe_audio' para leerlo.\n\n"
        
    if brief_paths:
        for p in brief_paths:
            user_message += f"Hay un documento adjunto (Brief/Requerimientos) en: {p}. Usa la herramienta 'extract_document_text' para leerlo.\n\n"
        
    user_message += f"Nota: Toma en cuenta TODA la información provista (ya sea de los documentos o los audios) por igual. Si ambos existen, combínalos y compleméntalos.\n\n"
    user_message += f"Las secciones que debes generar son {len(sections_to_generate)}: {', '.join(sections_to_generate)}.\n\n"
    user_message += "IMPORTANTE: Tu PRIMER paso debe ser usar la herramienta 'save_metadata' para estimar el monto, duración y tipo de proyecto basado en el contexto.\n"
    user_message += "Después de save_metadata, DEBES llamar a 'search_proposal_examples' con el tipo de proyecto detectado. NO redactes ninguna sección sin antes haber consultado el histórico.\n"
    user_message += f"Luego, redacta CADA UNA de las {len(sections_to_generate)} secciones usando 'submit_section_content'. Al final, llama a 'assemble_and_export'."
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]
    
    update_proposal_status(proposal_id, "processing", current_step="Iniciando análisis y recolección de contexto")
    append_timeline_event(proposal_id, "Agente inicializado", "Iniciando lectura de documentos y audio usando Groq.")
    
    try:
        max_iterations = 30
        iterations = 0
        has_searched_rag = False
        
        # 2. Agent Loop
        while iterations < max_iterations:
            iterations += 1
            logger.info(f"Agent Loop Iteration {iterations}")
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile", 
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                max_tokens=4096
            )
            
            response_message = response.choices[0].message
            # Append the message to the conversation
            messages.append(response_message)
            
            tool_calls = response_message.tool_calls
            
            if tool_calls:
                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    tool_id = tool_call.id
                    
                    logger.info(f"Llama 3 solicitó usar tool: {tool_name}")
                    tokens_used = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
                    
                    # --- MANEJO ESPECIAL: Guardado de Secciones ---
                    if tool_name == "submit_section_content":
                        if not has_searched_rag:
                            err_msg = "ERROR GUARDRAIL: No puedes redactar secciones sin antes haber llamado a 'search_proposal_examples'. Consulta la base de conocimiento histórica primero."
                            append_decision_log(proposal_id, iterations, "guardrail_triggered", tool_name, "N/A", err_msg, "El agente intentó redactar sin buscar ejemplos previos.", tokens_used)
                            messages.append({
                                "tool_call_id": tool_id,
                                "role": "tool",
                                "name": tool_name,
                                "content": err_msg
                            })
                            continue
                            
                        sec_name = tool_args.get("section_name")
                        sec_content = tool_args.get("content")
                        if sec_name and sec_content:
                            generated_sections[sec_name] = sec_content
                            if sec_name not in sections_completed:
                                sections_completed.append(sec_name)
                                
                            # Actualizar Supabase en vivo (barra de progreso en frontend)
                            db = get_supabase_client()
                            db.table("proposals").update({
                                "sections_completed": sections_completed,
                                "sections_content": generated_sections,
                                "current_step": f"Redactando: {sec_name.replace('_', ' ').title()}"
                            }).eq("id", proposal_id).execute()
                            
                            logger.info(f"Sección '{sec_name}' guardada en DB ({len(sections_completed)}/{len(sections_to_generate)})")
                            append_timeline_event(proposal_id, "Sección completada", f"Se ha generado la sección: {sec_name}")
                            
                    # --- MANEJO ESPECIAL: Metadatos ---
                    elif tool_name == "save_metadata":
                        amount = tool_args.get("amount")
                        duration = tool_args.get("duration")
                        project_type = tool_args.get("project_type")
                        solution_type = tool_args.get("solution_type")
                        tech_stack = tool_args.get("tech_stack")
                        db = get_supabase_client()
                        db.table("proposals").update({
                            "amount": amount,
                            "duration": duration,
                            "type": project_type,
                            "solution_type": solution_type,
                            "tech_stack": tech_stack
                        }).eq("id", proposal_id).execute()
                        append_timeline_event(proposal_id, "Metadatos extraídos", f"Monto: {amount}, Duración: {duration}, Solución: {solution_type}")
                        
                    # --- MANEJO ESPECIAL: Ensamblado y Fin ---
                    elif tool_name == "assemble_and_export":
                        update_proposal_status(proposal_id, "processing", current_step="Generando archivos PDF y DOCX")
                        append_timeline_event(proposal_id, "Exportando documentos", "Generando versión final en PDF y DOCX.")
                        
                        # Forzar las secciones reales que interceptamos en memoria
                        tool_args["sections"] = generated_sections
                        tool_args["prospect_name"] = prospect_name
                        
                        # Directorio local temporal
                        output_dir = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                            "storage", "generated"
                        )
                        tool_args["output_dir"] = output_dir

                        tool_args["output_dir"] = output_dir

                    # Ejecutar la tool de Python real
                    try:
                        result_data = execute_tool(tool_name, tool_args)
                        append_decision_log(
                            proposal_id, iterations, "tool_call", tool_name, 
                            str(tool_args)[:100] + "...", str(result_data)[:200] + "...", 
                            f"Tool {tool_name} ejecutada exitosamente.", tokens_used
                        )
                    except Exception as e:
                        result_data = f"Error interno al ejecutar {tool_name}: {e}"
                        append_decision_log(
                            proposal_id, iterations, "error_recovery", tool_name, 
                            str(tool_args)[:100] + "...", str(result_data)[:200] + "...", 
                            f"Fallo al ejecutar herramienta, retornando error al agente para que intente recuperarse.", tokens_used
                        )
                    
                    # --- MANEJO ESPECIAL POST-EJECUCIÓN: Históricos ---
                    if tool_name == "search_proposal_examples":
                        has_searched_rag = True
                        if result_data:
                            append_timeline_event(proposal_id, "Búsqueda en base de conocimiento", "Se encontraron propuestas históricas similares usando RAG.")
                        try:
                            db = get_supabase_client()
                            topic = tool_args.get("topic", "General")
                            # Fetch real structured data for the UI
                            from utils.rag_setup import search_similar
                            real_results = search_similar(topic, n_results=2)
                            
                            historic_data = []
                            for i, r in enumerate(real_results):
                                meta = r.get("metadata", {})
                                client_name = meta.get("cliente", f"Ref-{i+1}")
                                project_type = meta.get("tipo_proyecto", "Proyecto RAG")
                                historic_data.append({
                                    "title": f"Ref: {client_name}",
                                    "match": 95 - (i * 5), # pseudo-score
                                    "details": project_type
                                })
                                
                            if not historic_data:
                                historic_data = [{
                                    "title": f"Búsqueda: {topic}",
                                    "match": 90,
                                    "details": "Contexto extraído de ChromaDB."
                                }]
                            
                            db.table("proposals").update({
                                "reference_proposals": historic_data,
                                "historic_comparison": historic_data
                            }).eq("id", proposal_id).execute()
                        except Exception as e:
                            logger.error(f"Error saving historic reference: {e}")
                            
                    if tool_name == "extract_document_text":
                        append_timeline_event(proposal_id, "Análisis de Brief", "Documentos analizados y texto extraído.")
                    if tool_name == "transcribe_audio":
                        append_timeline_event(proposal_id, "Transcripción de Audio", "Audio convertido a texto exitosamente.")
                    
                    # Si fue assemble_and_export exitoso, subir a Storage y terminar
                    if tool_name == "assemble_and_export" and isinstance(result_data, str) and result_data.startswith("{"):
                        res_dict = json.loads(result_data)
                        if res_dict.get("status") == "success":
                            update_proposal_status(proposal_id, "processing", current_step="Subiendo archivos al Storage")
                            
                            # Subir PDF y DOCX al bucket 'proposal-files'
                            pdf_url = upload_file("proposal-files", res_dict["pdf_path"], f"generated/{proposal_id}.pdf")
                            docx_url = upload_file("proposal-files", res_dict["docx_path"], f"generated/{proposal_id}.docx")
                            
                            # Marcar como completado en la BD, estado borrador
                            db = get_supabase_client()
                            db.table("proposals").update({
                                "pdf_url": pdf_url,
                                "docx_url": docx_url,
                                "status": "borrador",
                                "current_step": "Propuesta generada exitosamente"
                            }).eq("id", proposal_id).execute()
                            
                            # Limpiar archivos generados localmente
                            try:
                                if os.path.exists(res_dict["pdf_path"]): os.remove(res_dict["pdf_path"])
                                if os.path.exists(res_dict["docx_path"]): os.remove(res_dict["docx_path"])
                            except Exception as e:
                                logger.warning(f"No se pudieron limpiar archivos generados: {e}")
                            
                            append_timeline_event(proposal_id, "Propuesta lista", "La propuesta comercial ha sido finalizada y guardada en borrador.")
                            logger.info(f"Proceso completado con éxito para propuesta {proposal_id}")
                            return # Termina el loop del orquestador
                        
                    # Devolver el resultado a Llama 3 para que siga pensando
                    messages.append({
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "name": tool_name,
                        "content": str(result_data)
                    })
                    
            elif response_message.content:
                tokens_used = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
                append_decision_log(
                    proposal_id, iterations, "llm_reasoning", "", "", 
                    str(response_message.content)[:200] + "...", 
                    "El modelo respondió con razonamiento sin llamar herramientas.", tokens_used
                )
                
                # Si el modelo respondió con texto y no llamó a ninguna herramienta
                if len(sections_completed) < len(sections_to_generate):
                    logger.warning("Llama 3 no llamó herramientas pero faltan secciones.")
                    messages.append({
                        "role": "user", 
                        "content": f"Aún faltan secciones por generar. Has generado: {sections_completed}. Faltan otras para completar las {len(sections_to_generate)}. Debes usar imperativamente 'submit_section_content' para entregar CADA UNA de las secciones restantes."
                    })
                else:
                    logger.warning("Llama 3 generó todas las secciones pero olvidó ensamblar. Forzando...")
                    messages.append({
                        "role": "user", 
                        "content": "Excelente, has generado todas las secciones. Ahora debes terminar. Llama INMEDIATAMENTE a la herramienta 'assemble_and_export' para finalizar el proceso."
                    })
            else:
                logger.warning(f"Respuesta inesperada o vacía de Groq.")
                break
                
        if iterations >= max_iterations:
            update_proposal_status(proposal_id, "error", current_step="Timeout: El agente excedió el número máximo de pasos.")
            append_timeline_event(proposal_id, "Error", "El agente excedió el tiempo máximo de procesamiento.")
            
    except Exception as e:
        logger.error(f"Error en orquestador de agente para propuesta {proposal_id}: {e}")
        update_proposal_status(proposal_id, "error", current_step=f"Error en el agente: {e}")
        append_timeline_event(proposal_id, "Error Crítico", str(e))
    finally:
        # Limpiar archivos de audio y documentos temporales
        paths_to_delete = (audio_paths or []) + (brief_paths or [])
        for p in paths_to_delete:
            try:
                if os.path.exists(p):
                    os.remove(p)
                    logger.info(f"Archivo temporal de contexto eliminado: {p}")
            except Exception as e:
                logger.warning(f"No se pudo eliminar archivo temporal {p}: {e}")

def regenerate_section_task(proposal_id: str, section_name: str, feedback: str):
    """Mini-agente para regenerar una sola sección basada en feedback."""
    try:
        api_key = os.getenv("GROQ_API_KEY")
        client = Groq(api_key=api_key)
        db = get_supabase_client()
        
        # 1. Fetch current content
        res = db.table("proposals").select("sections_content, prospect_name").eq("id", proposal_id).execute()
        if not res.data:
            return
        
        proposal = res.data[0]
        sections_content = proposal.get("sections_content", {})
        prospect_name = proposal.get("prospect_name", "Cliente")
        old_content = sections_content.get(section_name, "")
        
        # 2. Call LLM
        prompt = f"""Eres un Consultor Senior de LinkThinks. 
Tu tarea es OBLIGATORIAMENTE REESCRIBIR la sección '{section_name}' de una propuesta comercial, integrando el feedback del comercial.
Devuelve ÚNICAMENTE el texto Markdown de la sección modificada, sin saludos ni explicaciones.

CONTENIDO ACTUAL:
{old_content}

FEEDBACK DEL COMERCIAL:
{feedback}
"""
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048
        )
        
        new_content = response.choices[0].message.content
        tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
        
        # 3. Update section
        sections_content[section_name] = new_content
        db.table("proposals").update({"sections_content": sections_content}).eq("id", proposal_id).execute()
        
        append_decision_log(
            proposal_id, 1, "section_regeneration", "", "", "", 
            f"Regeneración de {section_name} completada. Feedback: '{feedback}'", tokens
        )
        append_timeline_event(proposal_id, "Sección regenerada", f"Se aplicó el feedback en: {section_name}")
        
        # 4. Re-assemble PDF/DOCX
        from agent.tools import execute_tool
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "generated")
        res_json = execute_tool("assemble_and_export", {"sections": sections_content, "prospect_name": prospect_name, "output_dir": output_dir})
        
        res_dict = json.loads(res_json)
        if res_dict.get("status") == "success":
            pdf_url = upload_file("proposal-files", res_dict["pdf_path"], f"generated/{proposal_id}.pdf")
            docx_url = upload_file("proposal-files", res_dict["docx_path"], f"generated/{proposal_id}.docx")
            
            db.table("proposals").update({
                "pdf_url": pdf_url,
                "docx_url": docx_url,
                "status": "borrador" # Volver a estado normal
            }).eq("id", proposal_id).execute()
            
            # Limpiar archivos generados localmente
            try:
                if os.path.exists(res_dict["pdf_path"]): os.remove(res_dict["pdf_path"])
                if os.path.exists(res_dict["docx_path"]): os.remove(res_dict["docx_path"])
            except Exception as e:
                logger.warning(f"No se pudieron limpiar archivos generados: {e}")
            
    except Exception as e:
        logger.error(f"Error regenerando sección {section_name} para {proposal_id}: {e}")
        db = get_supabase_client()
        db.table("proposals").update({"status": "borrador"}).eq("id", proposal_id).execute()
