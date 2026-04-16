from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone

from bson import ObjectId
from bson.errors import InvalidId

from ..mongo import obtener_bd
from ..decoradores import requiere_roles
from .correos import enviar_correo_ticket_tomado


@requiere_roles("TECNICO", "ADMIN")
def panel_tecnico(request):
    bd = obtener_bd()

    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        messages.error(request, "Sesión no válida.")
        return redirect("login")

    usuario_oid = ObjectId(usuario_id)

    # ---------------- FILTRO GENERAL POR TARJETA ----------------
    vista = request.GET.get("vista", "").strip()

    # ---------------- FILTROS ----------------
    q = request.GET.get("q", "").strip()
    laboratorio = request.GET.get("laboratorio", "").strip()
    categoria = request.GET.get("categoria", "").strip()
    estado = request.GET.get("estado", "").strip().upper()

    hoy = timezone.localdate()

    # Base: tickets sin asignar o asignados al técnico actual
    query = {
        "$or": [
            {"asignado_a": None},
            {"asignado_a": usuario_oid}
        ]
    }

    # ---------------- ATAJOS DESDE CONTADORES ----------------
    if vista == "mis_tickets":
        query = {"asignado_a": usuario_oid}

    elif vista == "nuevos":
        query["estado"] = "NUEVO"

    elif vista == "en_proceso":
        query = {
            "asignado_a": usuario_oid,
            "estado": "PROCESO"
        }

    elif vista == "resueltos_hoy":
        inicio_hoy = timezone.make_aware(
            timezone.datetime.combine(hoy, timezone.datetime.min.time())
        )
        fin_hoy = timezone.make_aware(
            timezone.datetime.combine(hoy, timezone.datetime.max.time())
        )

        query = {
            "asignado_a": usuario_oid,
            "estado": "RESUELTO",
            "meta.actualizado_en": {
                "$gte": inicio_hoy,
                "$lte": fin_hoy
            }
        }

    # ---------------- FILTROS ADICIONALES ----------------
    if laboratorio:
        try:
            query["laboratorio_id"] = ObjectId(laboratorio)
        except InvalidId:
            pass

    if categoria:
        try:
            query["categoria_id"] = ObjectId(categoria)
        except InvalidId:
            pass

    if estado in ["NUEVO", "REVISION", "PROCESO", "RESUELTO", "CERRADO"]:
        query["estado"] = estado

    if q:
        if "$and" not in query:
            query["$and"] = []

        query["$and"].append({
            "$or": [
                {"folio": {"$regex": q, "$options": "i"}},
                {"codigo": {"$regex": q, "$options": "i"}},
                {"descripcion": {"$regex": q, "$options": "i"}},
            ]
        })

    # ---------------- CATÁLOGOS ----------------
    labs = list(bd.catalogos_laboratorios.find({"activo": True}).sort("orden", 1))
    cats = list(bd.catalogos_categorias.find({"activo": True}).sort("orden", 1))

    lab_map = {str(x["_id"]): x["nombre"] for x in labs}
    cat_map = {str(x["_id"]): x["nombre"] for x in cats}

    # ---------------- USUARIOS ----------------
    usuarios_raw = list(bd.usuarios.find())
    user_map = {
        str(u["_id"]): u.get("perfil", {}).get("nombre", "Sin nombre")
        for u in usuarios_raw
    }

    # ---------------- KPIS ----------------
    tickets_base = list(
        bd.tickets.find({
            "$or": [
                {"asignado_a": None},
                {"asignado_a": usuario_oid}
            ]
        })
    )

    tickets_asignados = 0
    tickets_nuevos = 0
    tickets_proceso = 0
    tickets_resueltos_hoy = 0

    for t in tickets_base:
        asignado_a = t.get("asignado_a")
        estado_t = t.get("estado", "NUEVO")
        actualizado_en = t.get("meta", {}).get("actualizado_en")

        if asignado_a and str(asignado_a) == usuario_id:
            tickets_asignados += 1

        if estado_t == "NUEVO":
            tickets_nuevos += 1

        if asignado_a and str(asignado_a) == usuario_id and estado_t == "PROCESO":
            tickets_proceso += 1

        if (
            asignado_a
            and str(asignado_a) == usuario_id
            and estado_t == "RESUELTO"
            and actualizado_en
            and actualizado_en.date() == hoy
        ):
            tickets_resueltos_hoy += 1

    # ---------------- TICKETS ----------------
    tickets_raw = list(
        bd.tickets.find(query).sort("meta.actualizado_en", -1)
    )

    tickets = []

    for t in tickets_raw:
        asignado_a = t.get("asignado_a")
        actualizado_en = t.get("meta", {}).get("actualizado_en")

        tickets.append({
            "id": str(t["_id"]),
            "folio": t.get("folio", "—"),
            "laboratorio_nombre": lab_map.get(str(t.get("laboratorio_id")), "—"),
            "categoria_nombre": cat_map.get(str(t.get("categoria_id")), "—"),
            "codigo": t.get("codigo", "—"),
            "descripcion": t.get("descripcion", "—"),
            "prioridad": t.get("prioridad", "MEDIA"),
            "estado": t.get("estado", "NUEVO"),
            "tecnico": user_map.get(str(asignado_a), "Sin asignar") if asignado_a else "Sin asignar",
            "tecnico_id": str(asignado_a) if asignado_a else "",
            "actualizado_en": actualizado_en.strftime("%d-%b %H:%M") if actualizado_en else "—",
        })

    context = {
        "tickets": tickets,
        "laboratorios": [
            {"id": str(x["_id"]), "nombre": x["nombre"]}
            for x in labs
        ],
        "categorias": [
            {"id": str(x["_id"]), "nombre": x["nombre"]}
            for x in cats
        ],
        "tickets_asignados": tickets_asignados,
        "tickets_nuevos": tickets_nuevos,
        "tickets_proceso": tickets_proceso,
        "tickets_resueltos_hoy": tickets_resueltos_hoy,
        "vista_activa": vista,
    }

    return render(request, "tecnico.html", context)


@require_POST
@requiere_roles("TECNICO", "ADMIN")
def tomar_ticket(request, ticket_id):
    bd = obtener_bd()

    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        messages.error(request, "Sesión no válida.")
        return redirect("login")

    try:
        ticket_oid = ObjectId(ticket_id)
        tecnico_oid = ObjectId(usuario_id)
    except InvalidId:
        messages.error(request, "ID inválido.")
        return redirect("tecnico")

    ticket = bd.tickets.find_one({"_id": ticket_oid})
    if not ticket:
        messages.error(request, "Ticket no encontrado.")
        return redirect("tecnico")

    if ticket.get("asignado_a"):
        messages.error(request, "Este ticket ya fue asignado.")
        return redirect("tecnico")

    tecnico = bd.usuarios.find_one({
        "_id": tecnico_oid,
        "rol": "TECNICO",
        "estado.activo": True
    })

    if not tecnico:
        messages.error(request, "No tienes permisos para tomar tickets.")
        return redirect("tecnico")

    ahora = timezone.now()
    nombre_tecnico = tecnico.get("perfil", {}).get("nombre", "Técnico")

    nuevo_estado = ticket.get("estado", "NUEVO")
    if nuevo_estado == "NUEVO":
        nuevo_estado = "REVISION"

    bd.tickets.update_one(
        {"_id": ticket_oid},
        {
            "$set": {
                "asignado_a": tecnico_oid,
                "estado": nuevo_estado,
                "meta.actualizado_en": ahora,
            },
            "$push": {
                "historial": {
                    "accion": "TOMADO",
                    "estado": nuevo_estado,
                    "por": tecnico_oid,
                    "fecha": ahora,
                    "nota": f"Ticket tomado por {nombre_tecnico}"
                }
            }
        }
    )

    ticket_actualizado = {
        **ticket,
        "asignado_a": tecnico_oid,
        "estado": nuevo_estado,
    }

    try:
        enviado, error = enviar_correo_ticket_tomado(
            tecnico=tecnico,
            ticket=ticket_actualizado,
        )
    except Exception as e:
        enviado = False
        error = str(e)

    if enviado:
        messages.success(request, "Tomaste el ticket correctamente y se envió el correo.")
    else:
        messages.warning(
            request,
            f"Tomaste el ticket correctamente, pero no se pudo enviar el correo. {error}"
        )

    return redirect("tecnico")


@requiere_roles("TECNICO", "ADMIN")
def ticket_detalle_tecnico(request, ticket_id):
    bd = obtener_bd()

    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        messages.error(request, "Sesión no válida.")
        return redirect("login")

    try:
        ticket_oid = ObjectId(ticket_id)
        usuario_oid = ObjectId(usuario_id)
    except InvalidId:
        messages.error(request, "ID de ticket inválido.")
        return redirect("tecnico")

    ticket = bd.tickets.find_one({"_id": ticket_oid})
    if not ticket:
        messages.error(request, "Ticket no encontrado.")
        return redirect("tecnico")

    asignado_a = ticket.get("asignado_a")

    # El técnico solo puede ver tickets sin asignar o asignados a él
    if request.session.get("rol") == "TECNICO":
        if asignado_a is not None and asignado_a != usuario_oid:
            messages.error(request, "No tienes permiso para ver este ticket.")
            return redirect("tecnico")

    # Catálogos
    laboratorio_nombre = "—"
    categoria_nombre = "—"

    lab_id = ticket.get("laboratorio_id")
    cat_id = ticket.get("categoria_id")

    if lab_id:
        lab = bd.catalogos_laboratorios.find_one({"_id": lab_id})
        if lab:
            laboratorio_nombre = lab.get("nombre", "—")

    if cat_id:
        cat = bd.catalogos_categorias.find_one({"_id": cat_id})
        if cat:
            categoria_nombre = cat.get("nombre", "—")

    # Usuarios relacionados
    creado_por_nombre = "—"
    tecnico_nombre = "Sin asignar"

    creado_por = ticket.get("creado_por")
    if creado_por:
        usuario_creador = bd.usuarios.find_one({"_id": creado_por})
        if usuario_creador:
            creado_por_nombre = usuario_creador.get("perfil", {}).get("nombre", "—")

    if asignado_a:
        tecnico = bd.usuarios.find_one({"_id": asignado_a})
        if tecnico:
            tecnico_nombre = tecnico.get("perfil", {}).get("nombre", "Sin asignar")

    # Historial
    historial = []
    historial_raw = ticket.get("historial", [])

    for item in historial_raw:
        autor_nombre = "Sistema"
        autor_id = item.get("por")

        if autor_id:
            autor = bd.usuarios.find_one({"_id": autor_id})
            if autor:
                autor_nombre = autor.get("perfil", {}).get("nombre", "Usuario")

        fecha = item.get("fecha")
        historial.append({
            "estado": item.get("estado", ""),
            "nota": item.get("nota", "Sin nota"),
            "autor": autor_nombre,
            "fecha": fecha.strftime("%d-%b %H:%M") if fecha else "—",
        })

    detalle = {
        "id": str(ticket["_id"]),
        "folio": ticket.get("folio", "—"),
        "laboratorio_nombre": laboratorio_nombre,
        "categoria_nombre": categoria_nombre,
        "codigo": ticket.get("codigo", "—"),
        "descripcion": ticket.get("descripcion", "—"),
        "prioridad": ticket.get("prioridad", "MEDIA"),
        "estado": ticket.get("estado", "NUEVO"),
        "tecnico_nombre": tecnico_nombre,
        "creado_por_nombre": creado_por_nombre,
        "creado_en": ticket.get("meta", {}).get("creado_en"),
        "actualizado_en": ticket.get("meta", {}).get("actualizado_en"),
        "evidencias": ticket.get("evidencias", []),
    }

    context = {
        "ticket": {
            **detalle,
            "creado_en_fmt": detalle["creado_en"].strftime("%d-%b %H:%M") if detalle["creado_en"] else "—",
            "actualizado_en_fmt": detalle["actualizado_en"].strftime("%d-%b %H:%M") if detalle["actualizado_en"] else "—",
        },
        "historial": historial,
    }

    return render(request, "ticket_detalle_tecnico.html", context)


@requiere_roles("TECNICO", "ADMIN")
def ticket_gestionar(request, ticket_id):
    bd = obtener_bd()

    usuario_id = request.session.get("usuario_id")
    rol = request.session.get("rol")

    if not usuario_id:
        messages.error(request, "Sesión no válida.")
        return redirect("login")

    try:
        ticket_oid = ObjectId(ticket_id)
        usuario_oid = ObjectId(usuario_id)
    except InvalidId:
        messages.error(request, "ID inválido.")
        return redirect("tecnico")

    ticket = bd.tickets.find_one({"_id": ticket_oid})
    if not ticket:
        messages.error(request, "Ticket no encontrado.")
        return redirect("tecnico")

    asignado_a = ticket.get("asignado_a")

    if rol == "TECNICO":
        if not asignado_a or asignado_a != usuario_oid:
            messages.error(request, "Solo puedes gestionar tickets asignados a ti.")
            return redirect("tecnico")

    if request.method == "POST":
        nuevo_estado = request.POST.get("estado", "").strip().upper()
        nueva_prioridad = request.POST.get("prioridad", "").strip().upper()
        nota = request.POST.get("nota", "").strip()
        accion = request.POST.get("accion", "").strip()

        estados_validos = ["NUEVO", "REVISION", "PROCESO", "RESUELTO", "CERRADO"]
        prioridades_validas = ["ALTA", "MEDIA", "BAJA"]

        estado_actual = ticket.get("estado", "NUEVO")
        prioridad_actual = ticket.get("prioridad", "MEDIA")

        cambios_set = {
            "meta.actualizado_en": timezone.now()
        }
        historial_nuevos = []
        ahora = timezone.now()

        usuario = bd.usuarios.find_one({"_id": usuario_oid})
        nombre_usuario = "Técnico"
        if usuario:
            nombre_usuario = usuario.get("perfil", {}).get("nombre", "Técnico")

        # Cerrar ticket obliga estado CERRADO y nota
        if accion == "cerrar":
            if not nota:
                messages.error(request, "Debes escribir una nota final para cerrar el ticket.")
                return redirect("ticket_gestionar", ticket_id=ticket_id)

            cambios_set["estado"] = "CERRADO"

            historial_nuevos.append({
                "accion": "CERRADO",
                "estado": "CERRADO",
                "por": usuario_oid,
                "fecha": ahora,
                "nota": f"Ticket cerrado por {nombre_usuario}. Nota final: {nota}"
            })

            bd.tickets.update_one(
                {"_id": ticket_oid},
                {
                    "$set": cambios_set,
                    "$push": {"historial": {"$each": historial_nuevos}}
                }
            )

            messages.success(request, "Ticket cerrado correctamente.")
            return redirect("ticket_detalle_tecnico", ticket_id=ticket_id)

        # Cambio de estado
        if nuevo_estado in estados_validos and nuevo_estado != estado_actual:
            cambios_set["estado"] = nuevo_estado
            historial_nuevos.append({
                "accion": "CAMBIO_eSTADO",
                "estado": nuevo_estado,
                "por": usuario_oid,
                "fecha": ahora,
                "nota": f"Estado cambiado de {estado_actual} a {nuevo_estado}"
            })

        # Cambio de prioridad
        if nueva_prioridad in prioridades_validas and nueva_prioridad != prioridad_actual:
            cambios_set["prioridad"] = nueva_prioridad
            historial_nuevos.append({
                "accion": "CAMBIO_PRIORIDAD",
                "estado": cambios_set.get("estado", estado_actual),
                "por": usuario_oid,
                "fecha": ahora,
                "nota": f"Prioridad cambiada de {prioridad_actual} a {nueva_prioridad}"
            })

        # Nota de avance
        if nota:
            historial_nuevos.append({
                "accion": "NOTA",
                "estado": cambios_set.get("estado", estado_actual),
                "por": usuario_oid,
                "fecha": ahora,
                "nota": nota
            })

        # Evitar guardar vacío
        if len(cambios_set) == 1 and not historial_nuevos:
            messages.warning(request, "No realizaste cambios.")
            return redirect("ticket_gestionar", ticket_id=ticket_id)

        update_doc = {"$set": cambios_set}
        if historial_nuevos:
            update_doc["$push"] = {"historial": {"$each": historial_nuevos}}

        bd.tickets.update_one({"_id": ticket_oid}, update_doc)

        messages.success(request, "Ticket actualizado correctamente.")
        return redirect("ticket_detalle_tecnico", ticket_id=ticket_id)

    # GET: cargar datos para el formulario
    laboratorio_nombre = "—"
    categoria_nombre = "—"

    lab_id = ticket.get("laboratorio_id")
    cat_id = ticket.get("categoria_id")

    if lab_id:
        lab = bd.catalogos_laboratorios.find_one({"_id": lab_id})
        if lab:
            laboratorio_nombre = lab.get("nombre", "—")

    if cat_id:
        cat = bd.catalogos_categorias.find_one({"_id": cat_id})
        if cat:
            categoria_nombre = cat.get("nombre", "—")

    tecnico_nombre = "Sin asignar"
    if asignado_a:
        tecnico = bd.usuarios.find_one({"_id": asignado_a})
        if tecnico:
            tecnico_nombre = tecnico.get("perfil", {}).get("nombre", "Sin asignar")

    context = {
        "ticket": {
            "id": str(ticket["_id"]),
            "folio": ticket.get("folio", "—"),
            "laboratorio_nombre": laboratorio_nombre,
            "categoria_nombre": categoria_nombre,
            "codigo": ticket.get("codigo", "—"),
            "descripcion": ticket.get("descripcion", "—"),
            "prioridad": ticket.get("prioridad", "MEDIA"),
            "estado": ticket.get("estado", "NUEVO"),
            "tecnico_nombre": tecnico_nombre,
        },
        "estados": ["NUEVO", "REVISION", "PROCESO", "RESUELTO", "CERRADO"],
        "prioridades": ["ALTA", "MEDIA", "BAJA"],
    }

    return render(request, "ticket_gestionar_tecnico.html", context)