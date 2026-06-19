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
try:
    load_examples_on_startup()
except Exception as e:
    print(f"Error loading RAG examples on startup: {e}")

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
        
        # 2. Guardar archivos localmente (temporal para el agente) y en storage para la UI
        audio_paths = []
        docs_paths = []
        attachments = []
        
        for audio in audio_files:
            if audio and audio.filename:
                filename = secure_filename(f"{proposal_id}_{audio.filename}")
                audio_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                audio.save(audio_path)
                audio_paths.append(audio_path)
                from utils.supabase_client import upload_file
                url = upload_file("proposal-files", audio_path, f"attachments/{proposal_id}/{filename}")
                if url: attachments.append({"name": audio.filename, "url": url, "type": "audio"})
            
        for doc in docs_files:
            if doc and doc.filename:
                filename = secure_filename(f"{proposal_id}_doc_{doc.filename}")
                doc_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                doc.save(doc_path)
                docs_paths.append(doc_path)
                from utils.supabase_client import upload_file
                url = upload_file("proposal-files", doc_path, f"attachments/{proposal_id}/{filename}")
                if url: attachments.append({"name": doc.filename, "url": url, "type": "document"})
                
        if attachments:
            db.table("proposals").update({"attachments": attachments}).eq("id", proposal_id).execute()
            
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
            "reference_proposals": proposal.get("reference_proposals", []),
            "prospect_name": proposal.get("prospect_name", ""),
            "attachments": proposal.get("attachments", []),
            "solution_type": proposal.get("solution_type", ""),
            "tech_stack": proposal.get("tech_stack", ""),
            "agent_decision_log": proposal.get("agent_decision_log", [])
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

@app.route('/proposals/<proposal_id>/regenerate-section', methods=['POST'])
def regenerate_section(proposal_id):
    try:
        data = request.json
        if not data or 'section_name' not in data or 'feedback' not in data:
            return jsonify({"status": "error", "message": "Faltan parámetros 'section_name' o 'feedback'"}), 400
            
        section_name = data['section_name']
        feedback = data['feedback']
        
        # Actualizar estado a procesando (UI mostrará loader)
        update_proposal_status(proposal_id, "processing", current_step=f"Regenerando sección: {section_name}")
        
        # Lanzar tarea en background
        from agent.orchestrator import regenerate_section_task
        thread = threading.Thread(
            target=regenerate_section_task,
            args=(proposal_id, section_name, feedback)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "status": "success",
            "message": "Regeneración iniciada."
        }), 202
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/proposals/<proposal_id>/status', methods=['PATCH'])
def update_status(proposal_id):
    """
    Actualiza el estado de la propuesta.
    """
    try:
        data = request.json
        if not data or 'status' not in data:
            return jsonify({"status": "error", "message": "Falta el campo status"}), 400
        new_status = data['status']
        update_proposal_status(proposal_id, new_status, current_step=f"Estado actualizado a: {new_status}")
        return jsonify({"status": "success", "message": "Estado actualizado correctamente."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/proposals/<proposal_id>', methods=['DELETE'])
def delete_proposal(proposal_id):
    """
    Elimina una propuesta de la base de datos.
    """
    try:
        db = get_supabase_client()
        
        # Eliminar archivos del bucket primero
        try:
            paths_to_delete = [
                f"generated/{proposal_id}.pdf",
                f"generated/{proposal_id}.docx"
            ]
            
            # Listar adjuntos en la carpeta de la propuesta
            folder_path = f"attachments/{proposal_id}"
            files = db.storage.from_("proposal-files").list(folder_path)
            if files:
                for f in files:
                    # En algunos clientes el list retorna objetos, en otros dicts.
                    file_name = f.get('name') if isinstance(f, dict) else getattr(f, 'name', None)
                    if file_name and file_name != '.emptyFolderPlaceholder':
                        paths_to_delete.append(f"{folder_path}/{file_name}")
                        
            db.storage.from_("proposal-files").remove(paths_to_delete)
        except Exception as e:
            # No bloqueamos el borrado de BD si falla storage
            print(f"Advertencia: No se pudieron borrar algunos archivos de {proposal_id}: {e}")

        # Delete from RAG
        try:
            from utils.rag_setup import delete_from_rag
            delete_from_rag(proposal_id)
        except Exception as e:
            print(f"Advertencia: No se pudo eliminar la propuesta del RAG {proposal_id}: {e}")

        res = db.table("proposals").delete().eq("id", proposal_id).execute()
        return jsonify({"status": "success", "message": "Propuesta y sus archivos eliminados correctamente."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ATTACHMENTS ENDPOINTS ---
@app.route('/proposals/<proposal_id>/attachments', methods=['POST'])
def add_attachment(proposal_id):
    try:
        files = request.files.getlist("file")
        if not files:
            return jsonify({"status": "error", "message": "No files provided"}), 400
            
        db = get_supabase_client()
        res = db.table("proposals").select("attachments").eq("id", proposal_id).execute()
        if not res.data:
            return jsonify({"status": "error", "message": "Propuesta no encontrada"}), 404
            
        attachments = res.data[0].get("attachments", []) or []
        
        from utils.supabase_client import upload_file
        for f in files:
            if f and f.filename:
                filename = secure_filename(f"{proposal_id}_extra_{f.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                f.save(file_path)
                url = upload_file("proposal-files", file_path, f"attachments/{proposal_id}/{filename}")
                if url:
                    attachments.append({"name": f.filename, "url": url, "type": "document"})
                    
        db.table("proposals").update({"attachments": attachments}).eq("id", proposal_id).execute()
        return jsonify({"status": "success", "attachments": attachments}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/proposals/<proposal_id>/attachments/<filename>', methods=['DELETE'])
def delete_attachment(proposal_id, filename):
    try:
        db = get_supabase_client()
        res = db.table("proposals").select("attachments").eq("id", proposal_id).execute()
        if not res.data:
            return jsonify({"status": "error", "message": "Propuesta no encontrada"}), 404
            
        attachments = res.data[0].get("attachments", []) or []
        new_attachments = [a for a in attachments if a.get("name") != filename]
        
        db.table("proposals").update({"attachments": new_attachments}).eq("id", proposal_id).execute()
        return jsonify({"status": "success", "attachments": new_attachments}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- SETTINGS ENDPOINTS ---
@app.route('/settings/pricing', methods=['GET'])
def get_pricing_settings():
    try:
        db = get_supabase_client()
        res = db.table("settings").select("value").eq("key", "pricing_rates").execute()
        if res.data:
            return jsonify(res.data[0]["value"]), 200
        else:
            # Valores por defecto en caso de que no se haya corrido el insert
            return jsonify({"frontend": 600, "backend": 700, "design": 500, "pm": 600, "qa": 400}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/settings/pricing', methods=['PUT'])
def update_pricing_settings():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Datos requeridos"}), 400
        db = get_supabase_client()
        db.table("settings").upsert({"key": "pricing_rates", "value": data}).execute()
        return jsonify({"status": "success", "message": "Tarifas actualizadas correctamente."}), 200
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
