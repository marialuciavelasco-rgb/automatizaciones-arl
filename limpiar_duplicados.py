"""
Elimina registros duplicados en Firebase (mismo número de documento).
Conserva el más reciente por cada empleado.
Ejecutar con: python3 limpiar_duplicados.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from modules.firebase_client import _init_firebase, COLECCION

def main():
    print("\n=== LIMPIEZA DE DUPLICADOS ===\n")
    db = _init_firebase()
    docs = list(db.collection(COLECCION).stream())

    # Agrupar por número de documento
    por_documento = {}
    for d in docs:
        data = d.to_dict()
        num_doc = str(data.get("documento_empleado", "")).strip()
        if not num_doc:
            continue
        if num_doc not in por_documento:
            por_documento[num_doc] = []
        por_documento[num_doc].append((d.id, data))

    eliminados = 0
    for num_doc, registros in por_documento.items():
        if len(registros) <= 1:
            continue

        print(f"Duplicados encontrados para documento {num_doc}: {len(registros)} registros")

        # Ordenar: conservar primero completado, luego pendiente, luego el más reciente
        def prioridad(item):
            estado = item[1].get("estado", "")
            orden = {"completado": 0, "pendiente": 1, "requiere_intervencion": 2, "error": 3, "en_proceso": 4}
            return orden.get(estado, 99)

        registros_ordenados = sorted(registros, key=prioridad)
        conservar_id, conservar_data = registros_ordenados[0]

        print(f"  → Conservando: {conservar_id} ({conservar_data.get('estado')}) - {conservar_data.get('nombre_empleado')}")

        # Eliminar los demás
        for doc_id, data in registros_ordenados[1:]:
            print(f"  → Eliminando:  {doc_id} ({data.get('estado')})")
            db.collection(COLECCION).document(doc_id).delete()
            eliminados += 1

    if eliminados == 0:
        print("✅ No hay duplicados — todo limpio.")
    else:
        print(f"\n✅ Eliminados {eliminados} registros duplicados.")

if __name__ == "__main__":
    main()
