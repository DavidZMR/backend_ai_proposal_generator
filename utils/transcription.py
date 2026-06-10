"""
transcription.py — Integración con OpenAI Whisper para transcripción de audio.

Proporciona la funcionalidad para transcribir archivos de audio subidos por
los comerciales de LinkThinks, convirtiéndolos en texto que el agente pueda
procesar para generar las propuestas.
"""

import os
import logging
from groq import Groq
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Cargar variables de entorno (por si no se han cargado previamente)
load_dotenv()

def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe un archivo de audio a texto usando Groq Whisper API (modelo whisper-large-v3).
    Soporta los siguientes formatos: mp3, mp4, mpeg, mpga, m4a, wav, y webm.
    
    Args:
        audio_path: Ruta absoluta o relativa al archivo de audio.
        
    Returns:
        Texto transcrito en español.
        
    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si el formato de audio no es soportado o la API key falta.
        RuntimeError: Si ocurre un error de red o en la API de OpenAI.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Archivo de audio no encontrado: {audio_path}")
        
    # Validar extensión
    ext = os.path.splitext(audio_path)[1].lower()
    supported_formats = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}
    if ext not in supported_formats:
        raise ValueError(f"Formato de audio no soportado: {ext}. "
                         f"Formatos soportados: {', '.join(supported_formats)}")

    # Verificar API key
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY no está configurada en las variables de entorno.")

    # Advertencia de tamaño. Groq Whisper tiene un límite de 25MB.
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if file_size_mb > 25:
        logger.warning(f"El archivo {audio_path} excede los 25MB ({file_size_mb:.2f}MB). "
                       "La API limitará o rechazará el archivo.")

    client = Groq(api_key=api_key)

    try:
        with open(audio_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-large-v3", 
                file=(os.path.basename(audio_path), audio_file.read()),
                language="es" # Opcional pero recomendado para contexto LinkThinks
            )
        return response.text
    except Exception as e:
        logger.error(f"Error al transcribir el audio {audio_path} con Whisper: {e}")
        raise RuntimeError(f"Error en transcripción de audio: {e}")
