"""
Script de diagnóstico: muestra todos los registros en Firebase y su estado actual.
Ejecutar con: python3 diagnostico_firebase.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from modules.firebase_client import _init_firebase, COLECCION

def main():
    print("\n=== DIAGNÓSTICO FIREBASE ===\n")
    db = _init_firebase()
    docs = list(db.collection(COLECCION).stream())

    if not docs:
        print("⚠️  No hay documentos en la colección.")
        return

    print(f"Total registros encontrados: {len(docs)}\n")
    for d in docs:
        data = d.to_dict()
        print(f"  Nombre:          {data.get('nombre_empleado', 'N/D')}")
        print(f"  ID:              {data.get('id', d.id)}")
        print(f"  Estado:          {data.get('estado', 'N/D')}")
        print(f"  Campos faltantes: {data.get('campos_faltantes', [])}")
        print(f"  Campos manuales: {list(data.get('campos_manuales', {}).keys())}")
        print(f"  Intentos:        {data.get('intentos', 0)}")
        print()

if __name__ == "__main__":
    main()
