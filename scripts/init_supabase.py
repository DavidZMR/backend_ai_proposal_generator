import os
import sys

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.supabase_client import initialize_storage

if __name__ == "__main__":
    print("Iniciando creación de bucket 'proposal-files' en Supabase...")
    try:
        initialize_storage()
        print("¡Proceso completado con éxito!")
    except Exception as e:
        print(f"Error: {e}")
