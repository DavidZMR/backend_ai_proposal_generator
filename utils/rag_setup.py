"""
rag_setup.py — Inicialización y búsqueda en base de datos vectorial (ChromaDB).

Este módulo permite indexar propuestas comerciales pasadas para que
el agente pueda buscarlas por similitud semántica y utilizarlas
como referencia de estilo y contenido.
"""

import os
import json
import logging
import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "chromadb")
EXAMPLES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "examples")

client = None
collection = None

def initialize_chromadb():
    """Inicializa la conexión con ChromaDB y crea/carga la colección."""
    global client, collection
    
    os.makedirs(DB_PATH, exist_ok=True)
    
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # Usa un modelo ligero y eficiente en inglés/español
    sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    collection = client.get_or_create_collection(
        name="proposals",
        embedding_function=sentence_transformer_ef
    )
    logger.info("ChromaDB inicializado correctamente.")
    return collection

def index_proposal(file_path: str, proposal_id: str):
    """
    Convierte una propuesta JSON a texto y la indexa en ChromaDB.
    """
    global collection
    if not collection:
        initialize_chromadb()
        
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
                content_parts.append(f"[{sec_name.upper()}]\n{sec_content}")
            
    full_text = "\n".join(content_parts)
    
    metadata = {
        "file_path": file_path,
        "cliente": data.get("metadata", {}).get("cliente", "Desconocido"),
        "tipo_proyecto": data.get("metadata", {}).get("tipo_proyecto", "")
    }
    
    collection.upsert(
        documents=[full_text],
        metadatas=[metadata],
        ids=[proposal_id]
    )
    logger.info(f"Propuesta indexada en RAG: {proposal_id}")

def search_similar(query: str, n_results: int = 2) -> list:
    """
    Busca las propuestas más similares a la query dada.
    """
    global collection
    if not collection:
        initialize_chromadb()
        
    if collection.count() == 0:
        logger.warning("La colección ChromaDB está vacía.")
        return []
        
    # Limitar n_results al número total de documentos
    num_docs = collection.count()
    actual_n = min(n_results, num_docs)
        
    results = collection.query(
        query_texts=[query],
        n_results=actual_n
    )
    
    if not results or not results["documents"] or not results["documents"][0]:
        return []
        
    matched = []
    for i in range(len(results["documents"][0])):
        matched.append({
            "id": results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
        })
        
    return matched

def load_examples_on_startup():
    """
    Lee todos los JSON de la carpeta examples/ y los indexa.
    Ideal para ejecutar al inicio del servidor.
    """
    if not os.path.exists(EXAMPLES_PATH):
        logger.warning(f"No existe el directorio de ejemplos: {EXAMPLES_PATH}")
        return
        
    for filename in os.listdir(EXAMPLES_PATH):
        if filename.endswith(".json"):
            file_path = os.path.join(EXAMPLES_PATH, filename)
            proposal_id = filename.replace(".json", "")
            index_proposal(file_path, proposal_id)
