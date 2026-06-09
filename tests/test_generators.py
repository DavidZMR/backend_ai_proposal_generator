"""
Tests para generadores de documentos (DOCX y PDF)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.docx_builder import build_docx
from utils.pdf_converter import convert_sections_to_pdf

class TestGenerators(unittest.TestCase):
    
    def setUp(self):
        self.output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.prospect_name = "Cliente de Prueba S.A. de C.V."
        
        # Simulación de respuesta del LLM
        self.sections = {
            "resumen_ejecutivo": "Esta propuesta detalla el desarrollo de un portal inmobiliario.\n\nObjetivo: Mejorar las ventas digitales.",
            "alcance_funcional": "Módulos principales:\n- Buscador avanzado de propiedades\n- Panel administrativo\n- Integración con pagos",
            "arquitectura": "## Frontend\nReact.js con TailwindCSS.\n\n## Backend\nNode.js con Express.",
            "plan_sprints": "Sprint 1: Diseño UI/UX\nSprint 2: Backend\nSprint 3: Pruebas y despliegue",
            "inversion": "Costo total del proyecto:\n- Desarrollo: $200,000 MXN\n- Soporte: $15,000 MXN / mes\n\nTotal estimado: $215,000 MXN"
        }
        
    def test_build_docx(self):
        output_path = os.path.join(self.output_dir, "propuesta_prueba.docx")
        
        result_path = build_docx(self.sections, self.prospect_name, output_path)
        
        self.assertTrue(os.path.exists(result_path))
        self.assertEqual(result_path, output_path)
        
        # Validar tamaño del archivo (>0 bytes)
        self.assertGreater(os.path.getsize(result_path), 0)
        
        # Cleanup
        os.remove(result_path)
        
    def test_convert_sections_to_pdf(self):
        output_path = os.path.join(self.output_dir, "propuesta_prueba.pdf")
        
        result_path = convert_sections_to_pdf(self.sections, self.prospect_name, output_path)
        
        self.assertTrue(os.path.exists(result_path))
        self.assertEqual(result_path, output_path)
        
        # Validar tamaño del archivo (>0 bytes)
        self.assertGreater(os.path.getsize(result_path), 0)
        
        # Cleanup
        os.remove(result_path)

if __name__ == '__main__':
    unittest.main()
