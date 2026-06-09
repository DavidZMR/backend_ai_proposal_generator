"""
supabase_client.py — Cliente para interactuar con Supabase.

Maneja la persistencia de propuestas y el almacenamiento de archivos
generados (PDF, DOCX, Audios) en Supabase Storage.
"""

import os
import logging
from supabase import create_client, Client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Cargar variables
load_dotenv()

_supabase: Client = None

def get_supabase_client() -> Client:
    """Retorna un cliente singleton de Supabase usando SERVICE_ROLE."""
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL o SUPABASE_SERVICE_KEY no están configuradas en .env.")
        _supabase = create_client(url, key)
    return _supabase

def save_proposal(proposal_data: dict) -> dict:
    """
    Inserta o actualiza una propuesta.
    """
    try:
        client = get_supabase_client()
        response = client.table("proposals").upsert(proposal_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error guardando propuesta en Supabase: {e}")
        raise

def update_proposal_status(proposal_id: str, status: str, sections_completed: list = None, current_step: str = None) -> dict:
    """
    Actualiza el estado de generación de una propuesta para enviar progreso al frontend.
    """
    try:
        client = get_supabase_client()
        update_data = {"status": status}
        if sections_completed is not None:
            update_data["sections_completed"] = sections_completed
        if current_step is not None:
            update_data["current_step"] = current_step
            
        response = client.table("proposals").update(update_data).eq("id", proposal_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error actualizando status de propuesta en Supabase: {e}")
        raise

def get_proposal(proposal_id: str) -> dict:
    """Obtiene una propuesta por su ID."""
    try:
        client = get_supabase_client()
        response = client.table("proposals").select("*").eq("id", proposal_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error obteniendo propuesta {proposal_id}: {e}")
        raise

def list_proposals() -> list:
    """Obtiene el historial de propuestas."""
    try:
        client = get_supabase_client()
        response = client.table("proposals").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error listando propuestas: {e}")
        raise

def upload_file(bucket: str, file_path: str, destination_name: str) -> str:
    """
    Sube un archivo a Supabase Storage.
    Retorna la URL pública del archivo.
    """
    try:
        client = get_supabase_client()
        with open(file_path, "rb") as f:
            # Usar file_options upsert para evitar error si se reintenta
            client.storage.from_(bucket).upload(
                path=destination_name,
                file=f,
                file_options={"upsert": "true"}
            )
        return get_file_url(bucket, destination_name)
    except Exception as e:
        logger.error(f"Error subiendo archivo {file_path} al bucket {bucket}: {e}")
        raise

def get_file_url(bucket: str, file_path: str) -> str:
    """Obtiene URL pública del archivo."""
    client = get_supabase_client()
    return client.storage.from_(bucket).get_public_url(file_path)

def initialize_storage():
    """
    Crea el bucket 'proposal-files' si no existe y lo hace público.
    """
    try:
        client = get_supabase_client()
        buckets = client.storage.list_buckets()
        bucket_names = [b.name for b in buckets]
        
        if "proposal-files" not in bucket_names:
            logger.info("Creando bucket 'proposal-files'...")
            client.storage.create_bucket("proposal-files", {"public": True})
            logger.info("Bucket creado exitosamente.")
        else:
            logger.info("Bucket 'proposal-files' ya existe.")
    except Exception as e:
        logger.error(f"Error inicializando bucket en Supabase: {e}")
        raise

# --- TEMPLATES ---

def get_templates() -> list:
    try:
        client = get_supabase_client()
        response = client.table("templates").select("*").order("created_at", desc=False).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error obteniendo plantillas: {e}")
        raise

def create_template(template_data: dict) -> dict:
    try:
        client = get_supabase_client()
        response = client.table("templates").insert(template_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error creando plantilla: {e}")
        raise

def update_template(template_id: str, update_data: dict) -> dict:
    try:
        client = get_supabase_client()
        response = client.table("templates").update(update_data).eq("id", template_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error actualizando plantilla {template_id}: {e}")
        raise

def delete_template(template_id: str) -> bool:
    try:
        client = get_supabase_client()
        response = client.table("templates").delete().eq("id", template_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error eliminando plantilla {template_id}: {e}")
        raise

