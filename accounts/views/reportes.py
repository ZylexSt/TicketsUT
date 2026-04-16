from collections import defaultdict
from datetime import datetime, time

from django.utils import timezone

from bson import ObjectId

from ..mongo import obtener_bd


def asegurar_coleccion_reportes():
    bd = obtener_bd()

    if "reportes_generados" not in bd.list_collection_names():
        bd.create_collection("reportes_generados")

    # índices útiles para historial de reportes
    bd.reportes_generados.create_index("tipo")
    bd.reportes_generados.create_index("generado_en")
    bd.reportes_generados.create_index([("fecha_inicio", 1), ("fecha_fin", 1)])
    bd.reportes_generados.create_index("generado_por")

    return bd

def normalizar_datetime(fecha):
    if not fecha:
        return None

    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha, timezone.get_current_timezone())

    return timezone.localtime(fecha)

def obtener_fecha_minima_reportes():
    bd = obtener_bd()
    fechas = []

    primer_usuario = bd.usuarios.find_one(
        {"meta.creado_en": {"$exists": True}},
        {"meta": 1},
        sort=[("meta.creado_en", 1)]
    )
    if primer_usuario:
        fecha = normalizar_datetime(primer_usuario.get("meta", {}).get("creado_en"))
        if fecha:
            fechas.append(fecha)

    primer_ticket = bd.tickets.find_one(
        {"meta.creado_en": {"$exists": True}},
        {"meta": 1},
        sort=[("meta.creado_en", 1)]
    )
    if primer_ticket:
        fecha = normalizar_datetime(primer_ticket.get("meta", {}).get("creado_en"))
        if fecha:
            fechas.append(fecha)

    primer_acceso = bd.registros_acceso.find_one(
        {"fecha": {"$exists": True}},
        {"fecha": 1},
        sort=[("fecha", 1)]
    )
    if primer_acceso:
        fecha = normalizar_datetime(primer_acceso.get("fecha"))
        if fecha:
            fechas.append(fecha)

    if not fechas:
        return timezone.localdate()

    return min(fechas).date()


def parsear_periodo(fecha_inicio_txt, fecha_fin_txt):
    fecha_minima = obtener_fecha_minima_reportes()
    hoy = timezone.localdate()

    if not fecha_inicio_txt:
        fecha_inicio = fecha_minima
    else:
        fecha_inicio = datetime.strptime(fecha_inicio_txt, "%Y-%m-%d").date()

    if not fecha_fin_txt:
        fecha_fin = hoy
    else:
        fecha_fin = datetime.strptime(fecha_fin_txt, "%Y-%m-%d").date()

    # Limitar rango permitido
    if fecha_inicio < fecha_minima:
        fecha_inicio = fecha_minima
    if fecha_fin < fecha_minima:
        fecha_fin = fecha_minima

    if fecha_inicio > hoy:
        fecha_inicio = hoy
    if fecha_fin > hoy:
        fecha_fin = hoy

    if fecha_inicio > fecha_fin:
        fecha_inicio, fecha_fin = fecha_fin, fecha_inicio

    inicio = timezone.make_aware(
        datetime.combine(fecha_inicio, time.min),
        timezone.get_current_timezone()
    )
    fin = timezone.make_aware(
        datetime.combine(fecha_fin, time.max),
        timezone.get_current_timezone()
    )

    return fecha_inicio, fecha_fin, inicio, fin

def detectar_accion_historial(item):
    accion = (item.get("accion") or "").upper().strip()
    if accion:
        return accion

    # compatibilidad con historial viejo
    nota = (item.get("nota") or "").lower()
    estado = (item.get("estado") or "").upper()

    if "ticket tomado" in nota:
        return "TOMADO"
    if "ticket asignado" in nota:
        return "ASIGNADO"
    if estado == "CERRADO":
        return "CERRADO"
    if estado == "RESUELTO":
        return "RESUELTO"
    if estado == "PROCESO":
        return "PROCESO"
    if estado == "REVISION":
        return "REVISION"
    if estado == "NUEVO":
        return "CREADO"

    return "OTRO"


def construir_reporte_admin(fecha_inicio_txt, fecha_fin_txt):
    bd = asegurar_coleccion_reportes()
    fecha_inicio, fecha_fin, inicio, fin = parsear_periodo(fecha_inicio_txt, fecha_fin_txt)

    usuarios_raw = list(bd.usuarios.find())
    usuarios_map = {}

    for u in usuarios_raw:
        perfil = u.get("perfil", {})
        correo = perfil.get("correo")
        matricula = perfil.get("matricula")
        identificador = correo if correo else matricula if matricula else "—"

        usuarios_map[str(u["_id"])] = {
            "id": str(u["_id"]),
            "nombre": perfil.get("nombre", "Sin nombre"),
            "identificador": identificador,
            "rol": u.get("rol", "USUARIO"),
            "activo": u.get("estado", {}).get("activo", True),
            "creado_en": normalizar_datetime(u.get("meta", {}).get("creado_en")),
        }

    # KPIs base
    usuarios_creados = bd.usuarios.count_documents({
        "meta.creado_en": {"$gte": inicio, "$lte": fin}
    })

    tickets_creados_periodo = list(bd.tickets.find({
        "meta.creado_en": {"$gte": inicio, "$lte": fin}
    }))

    accesos_periodo = list(bd.registros_acceso.find({
        "fecha": {"$gte": inicio, "$lte": fin}
    }))

    # Accesos por usuario
    accesos_por_usuario = defaultdict(int)
    for acc in accesos_periodo:
        uid = str(acc.get("usuario_id"))
        accesos_por_usuario[uid] += 1

    # Tickets creados por usuario
    tickets_creados_por_usuario = defaultdict(int)
    for t in tickets_creados_periodo:
        creado_por = t.get("creado_por")
        if creado_por:
            tickets_creados_por_usuario[str(creado_por)] += 1

    # Actividad de técnicos por historial
    actividad_tecnicos = defaultdict(lambda: {
        "tomados": 0,
        "revision": 0,
        "proceso": 0,
        "resueltos": 0,
        "cerrados": 0,
    })

    tickets_con_historial = list(bd.tickets.find({
        "historial.fecha": {"$gte": inicio, "$lte": fin}
    }))

    tickets_cerrados_total = 0

    for ticket in tickets_con_historial:
        for item in ticket.get("historial", []):
            fecha = normalizar_datetime(item.get("fecha"))
            autor = item.get("por")

            if not fecha or fecha < inicio or fecha > fin:
                continue
            if not autor:
                continue

            uid = str(autor)
            usuario = usuarios_map.get(uid)
            if not usuario:
                continue

            accion = detectar_accion_historial(item)

            if accion == "CERRADO":
                tickets_cerrados_total += 1

            if usuario["rol"] != "TECNICO":
                continue

            if accion == "TOMADO":
                actividad_tecnicos[uid]["tomados"] += 1
            elif accion == "REVISION":
                actividad_tecnicos[uid]["revision"] += 1
            elif accion == "PROCESO":
                actividad_tecnicos[uid]["proceso"] += 1
            elif accion == "RESUELTO":
                actividad_tecnicos[uid]["resueltos"] += 1
            elif accion == "CERRADO":
                actividad_tecnicos[uid]["cerrados"] += 1

    usuarios_reporte = []
    tecnicos_reporte = []

    for uid, u in usuarios_map.items():
        creado_en_periodo = bool(
            u.get("creado_en") and inicio <= u["creado_en"] <= fin
        )
        accesos = accesos_por_usuario.get(uid, 0)
        tickets_creados = tickets_creados_por_usuario.get(uid, 0)

        if u["rol"] == "USUARIO":
            if creado_en_periodo or accesos > 0 or tickets_creados > 0:
                usuarios_reporte.append({
                    "nombre": u["nombre"],
                    "identificador": u["identificador"],
                    "accesos": accesos,
                    "tickets_creados": tickets_creados,
                    "creado_en_periodo": creado_en_periodo,
                })

        elif u["rol"] == "TECNICO":
            act = actividad_tecnicos.get(uid, {
                "tomados": 0,
                "revision": 0,
                "proceso": 0,
                "resueltos": 0,
                "cerrados": 0,
            })

            if (
                creado_en_periodo
                or accesos > 0
                or act["tomados"] > 0
                or act["revision"] > 0
                or act["proceso"] > 0
                or act["resueltos"] > 0
                or act["cerrados"] > 0
            ):
                tecnicos_reporte.append({
                    "nombre": u["nombre"],
                    "identificador": u["identificador"],
                    "accesos": accesos,
                    "tomados": act["tomados"],
                    "revision": act["revision"],
                    "proceso": act["proceso"],
                    "resueltos": act["resueltos"],
                    "cerrados": act["cerrados"],
                    "creado_en_periodo": creado_en_periodo,
                })

    usuarios_reporte.sort(key=lambda x: x["nombre"].lower())
    tecnicos_reporte.sort(key=lambda x: x["nombre"].lower())

    return {
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "generado_en": timezone.localtime(),
        "resumen": {
            "usuarios_creados": usuarios_creados,
            "accesos_totales": len(accesos_periodo),
            "tickets_creados": len(tickets_creados_periodo),
            "tickets_cerrados": tickets_cerrados_total,
        },
        "usuarios_reporte": usuarios_reporte,
        "tecnicos_reporte": tecnicos_reporte,
    }

    