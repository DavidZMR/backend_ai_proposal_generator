"""
orchestrator.py — Motor principal del agente que orquesta a Claude.

Maneja el loop de tool_use de la API de Anthropic, intercepta el guardado 
de secciones y coordina la subida final a Supabase.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any
import anthropic

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

def run_agent(proposal_id: str, prospect_name: str, audio_paths: list = None, transcript: str = None, brief_paths: list = None, template_id: int = None):
    """
    Ejecuta el loop principal del agente usando la API de Anthropic con tool_use.
    Esta función debe correr en un thread en background o una task queue.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        update_proposal_status(proposal_id, "error", current_step="Error: Falta API Key de Anthropic en .env")
        logger.error("Falta ANTHROPIC_API_KEY")
        return
        
    client = anthropic.Anthropic(api_key=api_key)
    
    generated_sections = {}
    sections_completed = []
    
    sections_to_generate = SECTIONS_LIST
    if template_id:
        try:
            db = get_supabase_client()
            res = db.table("templates").select("sections").eq("id", template_id).execute()
            if res.data:
                sections_to_generate = res.data[0].get("sections", SECTIONS_LIST)
        except Exception as e:
            logger.error(f"Error fetching template {template_id}: {e}")
    
    # 1. Construir mensaje inicial con el contexto disponible
    user_message = f"Por favor, genera una propuesta comercial para el prospecto: {prospect_name}.\n\n"
    
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
    user_message += f"Luego, redacta CADA UNA de las {len(sections_to_generate)} secciones usando 'submit_section_content'. Al final, llama a 'assemble_and_export'."
    
    messages = [{"role": "user", "content": user_message}]
    
    update_proposal_status(proposal_id, "processing", current_step="Iniciando análisis y recolección de contexto")
    append_timeline_event(proposal_id, "Agente inicializado", "Iniciando lectura de documentos y audio.")
    
    try:
        max_iterations = 30
        iterations = 0
        
        # 2. Agent Loop
        while iterations < max_iterations:
            iterations += 1
            logger.info(f"Agent Loop Iteration {iterations}")
            
            response = client.messages.create(
                model="claude-3-7-sonnet-20250219",  # Usando Claude 3.7 Sonnet (último modelo)
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS_SCHEMA
            )
            
            messages.append({"role": "assistant", "content": response.content})
            
            if response.stop_reason == "tool_use":
                tool_results = []
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_name = content_block.name
                        tool_args = content_block.input
                        tool_id = content_block.id
                        
                        logger.info(f"Claude solicitó usar tool: {tool_name}")
                        
                        # --- MANEJO ESPECIAL: Guardado de Secciones ---
                        if tool_name == "submit_section_content":
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
                            db = get_supabase_client()
                            db.table("proposals").update({
                                "amount": amount,
                                "duration": duration,
                                "type": project_type
                            }).eq("id", proposal_id).execute()
                            append_timeline_event(proposal_id, "Metadatos extraídos", f"Monto: {amount}, Duración: {duration}, Tipo: {project_type}")
                            
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

                        # Ejecutar la tool de Python real
                        result_data = execute_tool(tool_name, tool_args)
                        
                        # --- MANEJO ESPECIAL POST-EJECUCIÓN: Históricos ---
                        if tool_name == "search_proposal_examples" and result_data:
                            append_timeline_event(proposal_id, "Búsqueda en base de conocimiento", "Se encontraron propuestas históricas similares usando RAG.")
                            try:
                                # Parsear un poco el resultado para guardarlo
                                # En un caso real, la tool podría devolver JSON en vez de string para facilitar esto.
                                # Por ahora guardamos una versión simplificada.
                                db = get_supabase_client()
                                topic = tool_args.get("topic", "General")
                                historic_data = [{
                                    "title": f"Búsqueda: {topic}",
                                    "match": 90, # Simulado
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
                                
                                # Marcar como completado en la BD
                                db = get_supabase_client()
                                db.table("proposals").update({
                                    "pdf_url": pdf_url,
                                    "docx_url": docx_url,
                                    "status": "completed",
                                    "current_step": "Propuesta generada exitosamente"
                                }).eq("id", proposal_id).execute()
                                
                                append_timeline_event(proposal_id, "Propuesta lista", "La propuesta comercial ha sido finalizada y guardada.")
                                logger.info(f"Proceso completado con éxito para propuesta {proposal_id}")
                                return # Termina el loop del orquestador
                            
                        # Si no era la tool final, devolvemos el resultado a Claude para que siga pensando
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": str(result_data)
                        })
                        
                # Responder a Claude con los resultados de las tools
                messages.append({"role": "user", "content": tool_results})
                
            elif response.stop_reason == "end_turn":
                # Claude cree que ya terminó. Validar si faltó algo
                if len(sections_completed) < len(sections_to_generate):
                    logger.warning("Claude intentó terminar sin generar todas las secciones.")
                    messages.append({
                        "role": "user", 
                        "content": f"Aún faltan secciones por generar. Recuerda que son {len(sections_to_generate)} en total y debes usar 'submit_section_content' para cada una, y 'assemble_and_export' al final."
                    })
                else:
                    # Se detuvo sin llamar a exportar, forzar exportación
                    logger.warning("Claude generó todas las secciones pero olvidó ensamblar. Forzando...")
                    messages.append({
                        "role": "user", 
                        "content": "Excelente, has generado todas las secciones. Ahora, POR FAVOR, llama a la herramienta 'assemble_and_export'."
                    })
            else:
                logger.warning(f"Stop reason inesperado: {response.stop_reason}")
                break
                
        if iterations >= max_iterations:
            update_proposal_status(proposal_id, "error", current_step="Timeout: El agente excedió el número máximo de pasos.")
            append_timeline_event(proposal_id, "Error", "El agente excedió el tiempo máximo de procesamiento.")
            
    except Exception as e:
        logger.error(f"Error en orquestador de agente para propuesta {proposal_id}: {e}")
        update_proposal_status(proposal_id, "error", current_step=f"Error en el agente: {e}")
        append_timeline_event(proposal_id, "Error Crítico", str(e))
