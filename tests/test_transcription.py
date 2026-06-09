"""
Tests para utils/transcription.py
Ejecutar: python -m unittest tests.test_transcription
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.transcription import transcribe_audio

class TestTranscription(unittest.TestCase):
    
    def setUp(self):
        # Crear un archivo de audio dummy
        self.test_audio = "dummy_test_audio.mp3"
        with open(self.test_audio, "wb") as f:
            f.write(b"dummy audio content")
            
        # Set dummy API key para evitar error de validación
        os.environ["OPENAI_API_KEY"] = "sk-dummy-key"
            
    def tearDown(self):
        if os.path.exists(self.test_audio):
            os.remove(self.test_audio)
            
    def test_file_not_found(self):
        """Test: archivo inexistente lanza FileNotFoundError"""
        with self.assertRaises(FileNotFoundError):
            transcribe_audio("nonexistent.mp3")
            
    def test_unsupported_format(self):
        """Test: formato de archivo no soportado lanza ValueError"""
        dummy_txt = "dummy.txt"
        with open(dummy_txt, "w") as f:
            f.write("text")
            
        with self.assertRaises(ValueError):
            transcribe_audio(dummy_txt)
            
        os.remove(dummy_txt)
        
    @patch('utils.transcription.OpenAI')
    def test_transcribe_success(self, MockOpenAI):
        """Test: el proceso de transcripción mockeado es exitoso"""
        # Setup mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Esta es una transcripción de prueba."
        mock_client.audio.transcriptions.create.return_value = mock_response
        MockOpenAI.return_value = mock_client
        
        result = transcribe_audio(self.test_audio)
        self.assertEqual(result, "Esta es una transcripción de prueba.")
        
if __name__ == '__main__':
    unittest.main()
