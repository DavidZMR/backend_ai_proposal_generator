"""
Test rápido de utils/doc_reader.py
Ejecutar: python -m tests.test_doc_reader
"""
import os
import sys
import json

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.doc_reader import extract_text_from_file


def test_read_txt():
    """Test: lectura de archivo .txt"""
    test_file = os.path.join("tests", "fixtures", "sample.txt")
    os.makedirs(os.path.dirname(test_file), exist_ok=True)

    # Crear archivo de prueba
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("Esta es una prueba de lectura de texto.\n")
        f.write("Línea 2: con acentos y ñ.\n")
        f.write("Línea 3: montos $250,000 MXN.\n")

    result = extract_text_from_file(test_file)
    assert "prueba de lectura" in result
    assert "acentos y ñ" in result
    assert "$250,000 MXN" in result
    print(f"  [OK] test_read_txt -- ({len(result)} chars)")

    # Cleanup
    os.remove(test_file)


def test_read_json():
    """Test: lectura de archivo .json (propuesta histórica)"""
    test_file = os.path.join("tests", "fixtures", "sample_proposal.json")
    os.makedirs(os.path.dirname(test_file), exist_ok=True)

    # Crear JSON de prueba con estructura de propuesta
    proposal = {
        "metadata": {
            "cliente": "Empresa Test S.A. de C.V.",
            "monto": "$150,000 MXN",
            "duracion": "3 meses",
            "estado": "ganada"
        },
        "secciones": {
            "resumen_ejecutivo": "Propuesta para desarrollar un sistema de gestión de inventarios.",
            "alcance_funcional": [
                "Módulo de inventario",
                "Módulo de reportes",
                "Dashboard administrativo"
            ],
            "inversion": {
                "desarrollo": "$120,000 MXN",
                "qa": "$20,000 MXN",
                "pm": "$10,000 MXN"
            }
        }
    }

    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)

    result = extract_text_from_file(test_file)
    assert "Empresa Test" in result
    assert "$150,000 MXN" in result
    assert "Resumen Ejecutivo" in result.upper() or "RESUMEN EJECUTIVO" in result
    assert "inventarios" in result
    print(f"  [OK] test_read_json -- ({len(result)} chars)")

    # Cleanup
    os.remove(test_file)


def test_unsupported_format():
    """Test: formato no soportado lanza ValueError"""
    try:
        extract_text_from_file("archivo.xyz")
    except (ValueError, FileNotFoundError):
        print("  [OK] test_unsupported_format -- (excepcion correcta)")
        return
    raise AssertionError("Debería haber lanzado ValueError o FileNotFoundError")


def test_file_not_found():
    """Test: archivo inexistente lanza FileNotFoundError"""
    try:
        extract_text_from_file("no_existe.pdf")
    except FileNotFoundError:
        print("  [OK] test_file_not_found -- (FileNotFoundError)")
        return
    raise AssertionError("Debería haber lanzado FileNotFoundError")


if __name__ == "__main__":
    print("\n=== Tests de doc_reader.py ===")

    test_read_txt()
    test_read_json()
    test_unsupported_format()
    test_file_not_found()

    print("\n=== Todos los tests pasaron! ===")
