"""
Mappings de datos: Excel → Portal ARL
Basado en análisis del Excel "Notificaciones Nómina Buk.xlsx"
"""

# ─────────────────────────────────────────────
# EMPRESA: Excel → Código ARL exacto
# ─────────────────────────────────────────────
EMPRESA_MAP = {
    "BIA TECHNOLOGIES SAS":  "NT-901637465-BIA TECHNOLOGIES S.A.S",
    "BIA ENERGY SAS ESP":    "NT-901588412-BIA ENERGY S.A.S. E.S.P",
}

# ─────────────────────────────────────────────
# TIPO DE DOCUMENTO: Excel → Portal
# ─────────────────────────────────────────────
TIPO_DOC_MAP = {
    "CC":  "CEDULA DE CIUDADANIA",
    "CE":  "CEDULA DE EXTRANJERIA",
    "PA":  "PASAPORTE",
    "TI":  "TARJETA DE IDENTIDAD",
    "NIT": "NIT",
}

# ─────────────────────────────────────────────
# GÉNERO: Excel → Portal
# ─────────────────────────────────────────────
GENERO_MAP = {
    "MASCULINO": "MASCULINO",
    "FEMENINO":  "FEMENINO",
    "M":         "MASCULINO",
    "F":         "FEMENINO",
}

# ─────────────────────────────────────────────
# EPS: Normalización → nombre canónico
# Los valores del portal se descubren en tiempo de ejecución.
# Este diccionario mapea variantes del Excel al nombre canónico
# que luego se busca en las opciones reales del portal.
# ─────────────────────────────────────────────
EPS_NORMALIZE = {
    # SANITAS
    "SANITAS":       "EPS SANITAS",
    "EPS SANITAS":   "EPS SANITAS",
    "SANITAS EPS":   "EPS SANITAS",

    # SURA
    "SURA":          "EPS SURA",
    "EPS SURA":      "EPS SURA",
    "SURAMERICANA":  "EPS SURA",

    # COMPENSAR
    "COMPENSAR":     "COMPENSAR",
    "EPS COMPENSAR": "COMPENSAR",

    # SALUD TOTAL
    "SALUD TOTAL":   "SALUD TOTAL",
    "SALUDTOTAL":    "SALUD TOTAL",
    "SLUD TOTAL":    "SALUD TOTAL",  # typo del Excel

    # FAMISANAR
    "FAMISANAR":     "FAMISANAR",

    # NUEVA EPS
    "NUEVA EPS":     "NUEVA EPS",
    "NUEVA EPS S.A": "NUEVA EPS",

    # ALIANSALUD
    "ALIANSALUD":    "ALIANSALUD",
    "ALIANSALUD EPS":"ALIANSALUD",

    # COOSALUD
    "COOSALUD":      "COOSALUD",

    # CAPITAL SALUD
    "CAPITAL SALUD": "CAPITAL SALUD",
    "CAPITALSALUD":  "CAPITAL SALUD",

    # COMFENALCO
    "COMFENALCO":    "COMFENALCO VALLE",

    # MUTUALSER
    "MUTUALSER":     "MUTUALSER",

    # MALLAMAS
    "MALLAMAS":      "MALLAMAS",

    # MEDIMAS
    "MEDIMAS":       "MEDIMAS EPS",

    # ESPECIALES
    "N.A":           None,
    "NO APLICA":     None,
    "NA":            None,
}

# ─────────────────────────────────────────────
# AFP (PENSIONES): Normalización → nombre canónico
# ─────────────────────────────────────────────
AFP_NORMALIZE = {
    # COLPENSIONES
    "COLPENSIONES":  "COLPENSIONES",
    "COLPENSION":    "COLPENSIONES",

    # PORVENIR
    "PORVENIR":      "PORVENIR",
    "POVERNIR":      "PORVENIR",  # typo del Excel
    "´PORVENIR":     "PORVENIR",  # typo del Excel

    # PROTECCIÓN
    "PROTECCION":    "PROTECCION",
    "PROTECCIÓN":    "PROTECCION",

    # COLFONDOS
    "COLFONDOS":     "COLFONDOS",

    # SKANDIA / OLD MUTUAL
    "SKANDIA":       "SKANDIA",
    "OLD MUTUAL":    "SKANDIA",

    # ESPECIALES
    "N.A":           None,
    "NO APLICA":     None,
    "NA":            None,
}

# ─────────────────────────────────────────────
# CIUDADES: Normalización → nombre canónico
# ─────────────────────────────────────────────
CIUDAD_NORMALIZE = {
    # BOGOTÁ
    "BOGOTA":                    "BOGOTA",
    "BOGOTÁ":                    "BOGOTA",
    "BOGOTA D.C":                "BOGOTA",
    "BOGOTÁ D.C":                "BOGOTA",
    "BOGOTÁ D.C.":               "BOGOTA",
    "BOGOTÁ DC":                 "BOGOTA",
    "BOGOTÁ, D.C. (BOGOTA)":     "BOGOTA",
    "BOGOTA D.C.":               "BOGOTA",

    # BARRANQUILLA
    "BARRANQUILLA":              "BARRANQUILLA",
    "BARRANQUILLA, ATLÁNTICO":   "BARRANQUILLA",
    "BARRANQUILLA ATLÁNTICO":    "BARRANQUILLA",

    # MEDELLÍN
    "MEDELLIN":                  "MEDELLIN",
    "MEDELLÍN":                  "MEDELLIN",
    "MEDELLÍN, ANTIOQUIA":       "MEDELLIN",

    # BELLO (municipio de Antioquia)
    "BELLO":                     "BELLO",
    "BELLO, ANTIOQUIA":          "BELLO",

    # ITAGÜÍ
    "ITAGUI":                    "ITAGUI",
    "ITAGÜÍ":                    "ITAGUI",

    # CARTAGENA
    "CARTAGENA":                 "CARTAGENA",

    # CALI
    "CALI":                      "CALI",

    # PEREIRA
    "PEREIRA":                   "PEREIRA",

    # IBAGUÉ
    "IBAGUE":                    "IBAGUE",
    "IBAGUÉ":                    "IBAGUE",

    # ARMENIA
    "ARMENIA":                   "ARMENIA",

    # POPAYÁN
    "POPAYAN":                   "POPAYAN",
    "POPAYÁN":                   "POPAYAN",

    # TUNJA
    "TUNJA":                     "TUNJA",

    # VILLAPINZÓN
    "VILLAPINZON":               "VILLAPINZON",
    "VILLAPINZÓN":               "VILLAPINZON",
}

# ─────────────────────────────────────────────
# VALORES FIJOS (siempre iguales en el portal)
# ─────────────────────────────────────────────
VALORES_FIJOS = {
    "tipo_cotizante":    "1-DEPENDIENTE",
    "subtipo_cotizante": "0 - No aplica",
    "centro_trabajo":    "1 - PRINCIPAL",
    "tipo_salario":      "FIJO",
    "forma_pago":        "VENCIDO",
    "jornada":           "UNICA",
    "zona":              "URBANA",
}

# ─────────────────────────────────────────────
# MODALIDAD: Inferencia desde datos del Excel
# (modalidad no existe en Excel → va al dashboard)
# ─────────────────────────────────────────────
MODALIDAD_OPTIONS = [
    "PRESENCIAL",
    "TELETRABAJO",
    "TRABAJO EN CASA",
]

# ─────────────────────────────────────────────
# COLUMNAS DEL EXCEL que necesitamos
# (key interno → nombre real en el Excel)
# ─────────────────────────────────────────────
EXCEL_COLUMNS = {
    "colaborador":  "Colaborador",
    "genero":       "Género",
    "tipo_salario": "Tipo de salario",
    "salario":      "Salario",
    "aux_rod":      "Aux. Rodamiento",
    "fecha_ingreso":"Fecha de ingreso",
    "cargo":        "Cargo",
    "tipo_doc":     "Tipo de documento",
    "numero_doc":   "Número de documento",
    "telefono":     "Teléfono",
    "email":        "Email Personal",
    "ciudad":       "Ciudad de servicio",   # con trailing space en Excel
    "direccion":    "Dirección",
    "eps":          "EPS",
    "afp":          "Pensiones",
    "compania":     "Compañía",
    "arl_status":   "Status",               # columna ARL Status
}
