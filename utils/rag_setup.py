"""
rag_setup.py — Búsqueda en base de datos vectorial mediante Supabase y Sentence-Transformers locales.

Este módulo permite indexar propuestas comerciales pasadas usando embeddings generados
mediante la librería sentence-transformers (localmente) y almacenados en Supabase (pgvector),
evitando por completo el uso y memoria de ChromaDB.
"""

import os
import json
import logging
from sentence_transformers import SentenceTransformer
from utils.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

EXAMPLES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "examples")

# Inicialización perezosa (lazy load) del modelo para no bloquear el inicio ni consumir memoria hasta que se necesite
_model = None

def get_model():
    """Carga el modelo de embeddings en memoria solo cuando se requiere."""
    global _model
    if _model is None:
        logger.info("Cargando modelo sentence-transformers en memoria...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def get_embedding(text: str) -> list:
    """Obtiene el embedding numérico de un texto usando el modelo local."""
    try:
        model = get_model()
        # encode retorna un numpy array, lo convertimos a lista plana
        vector = model.encode(text).tolist()
        return vector
    except Exception as e:
        logger.error(f"Error generando embedding localmente: {e}")
        return [0.0] * 384

def index_proposal(file_path: str, proposal_id: str):
    """
    Convierte una propuesta JSON a texto y la indexa en Supabase.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        content_parts = []
        if "metadata" in data:
            for k, v in data["metadata"].items():
                content_parts.append(f"{k}: {v}")
                
        content_parts.append("")
        
        if "secciones" in data:
            for sec_name, sec_content in data["secciones"].items():
                if isinstance(sec_content, str):
                    # Solo guardar un extracto compacto de cada sección (máx 300 chars)
                    # para evitar documentos enormes que inflan el consumo de tokens al buscar
                    trimmed = sec_content[:300].strip()
                    if len(sec_content) > 300:
                        trimmed += "..."
                    content_parts.append(f"[{sec_name.upper()}]\n{trimmed}")
                
        full_text = "\n".join(content_parts)
        metadata = {
            "file_path": file_path,
            "cliente": data.get("metadata", {}).get("cliente", "Desconocido"),
            "tipo_proyecto": data.get("metadata", {}).get("tipo_proyecto", "")
        }
        
        embedding = get_embedding(full_text)
        client = get_supabase_client()
        
        # Eliminamos primero si existe (simular upsert manual por proposal_id)
        client.table("proposal_embeddings").delete().eq("proposal_id", proposal_id).execute()
        
        client.table("proposal_embeddings").insert({
            "proposal_id": proposal_id,
            "document": full_text,
            "metadata": metadata,
            "embedding": embedding
        }).execute()
        
        logger.info(f"Propuesta indexada en Supabase RAG: {proposal_id}")
    except Exception as e:
        logger.error(f"Error indexando propuesta {proposal_id}: {e}")

def delete_from_rag(proposal_id: str):
    """
    Elimina una propuesta de Supabase por su proposal_id.
    """
    try:
        client = get_supabase_client()
        client.table("proposal_embeddings").delete().eq("proposal_id", proposal_id).execute()
        logger.info(f"Propuesta eliminada de Supabase RAG: {proposal_id}")
    except Exception as e:
        logger.error(f"Error al eliminar de RAG: {e}")
        
    json_path = os.path.join(EXAMPLES_PATH, f"{proposal_id}.json")
    if os.path.exists(json_path):
        try:
            os.remove(json_path)
            logger.info(f"Archivo JSON eliminado de examples: {json_path}")
        except Exception as e:
            logger.error(f"Error al eliminar archivo JSON {json_path}: {e}")

def search_similar(query: str, n_results: int = 2) -> list:
    """
    Busca las propuestas más similares usando pgvector en Supabase.
    """
    try:
        query_embedding = get_embedding(query)
        client = get_supabase_client()
        
        # Llamar a la función RPC que crearemos en Supabase
        res = client.rpc("match_proposals", {
            "query_embedding": query_embedding,
            "match_count": n_results
        }).execute()
        
        if not res.data:
            return []
            
        matched = []
        for item in res.data:
            matched.append({
                "id": item["proposal_id"],
                "document": item["document"],
                "metadata": item["metadata"]
            })
            
        return matched
    except Exception as e:
        logger.error(f"Error buscando similitudes en Supabase: {e}")
        return []

def load_examples_on_startup():
    """
    Lee todos los JSON de la carpeta examples/ y los indexa si no están en Supabase.
    """
    if not os.path.exists(EXAMPLES_PATH):
        logger.warning(f"No existe el directorio de ejemplos: {EXAMPLES_PATH}")
        return
        
    client = get_supabase_client()
    try:
        res = client.table("proposal_embeddings").select("proposal_id").execute()
        existing_ids = [item["proposal_id"] for item in res.data] if res.data else []
    except Exception as e:
        logger.error(f"No se pudo consultar Supabase (posiblemente falta la tabla): {e}")
        return
        
    for filename in os.listdir(EXAMPLES_PATH):
        if filename.endswith(".json"):
            file_path = os.path.join(EXAMPLES_PATH, filename)
            proposal_id = filename.replace(".json", "")
            if proposal_id not in existing_ids:
                index_proposal(file_path, proposal_id)
