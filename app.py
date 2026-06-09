"""
app.py — API REST del Backend (Flask)

Expone los endpoints para interactuar con el Agente desde el Frontend.
"""

import os
import threading
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from utils.supabase_client import (
    get_supabase_client, update_proposal_status, list_proposals,
    get_templates, create_template, update_template, delete_template
)
from utils.rag_setup import load_examples_on_startup
from agent.orchestrator import run_agent

# Cargar entorno
load_dotenv()

app = Flask(__name__)
# Configurar CORS para permitir requests del frontend local y en producción
CORS(app, resources={r"/*": {"origins": "*"}})

# Configuración de subidas temporales
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage', 'sessions')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Inicializar RAG al arrancar el servidor
# load_examples_on_startup() # Se puede descomentar en producción, para dev lo mantenemos rápido

@app.route('/proposals', methods=['GET'])
def get_proposals():
    try:
        proposals_list = list_proposals()
        return jsonify(proposals_list), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/proposals', methods=['POST'])
def create_proposal():
    """
    Recibe la solicitud inicial, guarda los archivos temporales, 
    crea el registro en Supabase y lanza el agente en background.
    """
    try:
        prospect_name = request.form.get("prospect_name", "Cliente Sin Nombre")
        transcript = request.form.get("transcript", "")
        template_id = request.form.get("template_id", None)
        
        audio_files = request.files.getlist("audio")
        docs_files = request.files.getlist("docs")
            
        # 1. Crear registro inicial en Supabase
        db = get_supabase_client()
        proposal_data = {
            "prospect_name": prospect_name,
            "status": "processing",
            "current_step": "Inicializando",
            "transcript": transcript,
            "template_id": int(template_id) if template_id else None
        }
        res = db.table("proposals").insert(proposal_data).execute()
        proposal_id = res.data[0]["id"]
        
        # 2. Guardar archivos localmente (temporal para el agente)
        audio_paths = []
        docs_paths = []
        
        for audio in audio_files:
            if audio and audio.filename:
                filename = secure_filename(f"{proposal_id}_{audio.filename}")
                audio_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                audio.save(audio_path)
                audio_paths.append(audio_path)
            
        for doc in docs_files:
            if doc and doc.filename:
                filename = secure_filename(f"{proposal_id}_doc_{doc.filename}")
                doc_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                doc.save(doc_path)
                docs_paths.append(doc_path)
            
        # 3. Lanzar el agente en un Thread separado
        # Pasamos template_id para que el orquestador lo use
        thread = threading.Thread(
            target=run_agent,
            args=(proposal_id, prospect_name, audio_paths, transcript, docs_paths, template_id)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "status": "success",
            "proposal_id": proposal_id,
            "message": "Agente iniciado correctamente."
        }), 202
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/proposals/<proposal_id>/status', methods=['GET'])
def get_proposal_status(proposal_id):
    """
    Retorna el estado actual de la propuesta consultando a Supabase.
    """
    try:
        db = get_supabase_client()
        res = db.table("proposals").select("*").eq("id", proposal_id).execute()
        
        if not res.data:
            return jsonify({"status": "error", "message": "Propuesta no encontrada."}), 404
            
        proposal = res.data[0]
        
        return jsonify({
            "proposal_id": proposal["id"],
            "status": proposal["status"],
            "current_step": proposal.get("current_step", ""),
            "sections_completed": proposal.get("sections_completed", []),
            "sections_content": proposal.get("sections_content", {}),
            "timeline_events": proposal.get("timeline_events", []),
            "historic_comparison": proposal.get("historic_comparison", []),
            "reference_proposals": proposal.get("reference_proposals", [])
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/proposals/<proposal_id>/download', methods=['GET'])
def download_proposal(proposal_id):
    """
    Descarga el PDF o DOCX de la propuesta generada.
    ?format=pdf (default) o docx
    """
    try:
        format_type = request.args.get("format", "pdf").lower()
        if format_type not in ["pdf", "docx"]:
            return jsonify({"status": "error", "message": "Formato inválido. Usa pdf o docx."}), 400
            
        db = get_supabase_client()
        res = db.table("proposals").select("pdf_url, docx_url").eq("id", proposal_id).execute()
        
        if not res.data:
            return jsonify({"status": "error", "message": "Propuesta no encontrada."}), 404
            
        proposal = res.data[0]
        url = proposal.get(f"{format_type}_url")
        
        if not url:
            return jsonify({"status": "error", "message": "El archivo aún no ha sido generado."}), 404
            
        # Retornar la URL pública de Supabase Storage para que el cliente la descargue
        return jsonify({
            "status": "success",
            "download_url": url
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/proposals/<proposal_id>/send', methods=['POST'])
def send_proposal(proposal_id):
    """
    Simula el envío de la propuesta por correo.
    Actualiza el estado en BD a 'enviada'.
    """
    try:
        # TODO: Implementar SMTP real aquí.
        update_proposal_status(proposal_id, "enviada", current_step="Enviada a revisión por correo")
        return jsonify({"status": "success", "message": "Propuesta enviada por correo simulado."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- TEMPLATES ENDPOINTS ---
@app.route('/templates', methods=['GET'])
def list_templates():
    try:
        return jsonify(get_templates()), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/templates', methods=['POST'])
def add_template():
    try:
        data = request.json
        if not data or 'name' not in data or 'category' not in data:
            return jsonify({"status": "error", "message": "Faltan campos requeridos"}), 400
        result = create_template(data)
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/templates/<template_id>', methods=['PUT'])
def edit_template(template_id):
    try:
        data = request.json
        result = update_template(template_id, data)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/templates/<template_id>', methods=['DELETE'])
def remove_template(template_id):
    try:
        delete_template(template_id)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
