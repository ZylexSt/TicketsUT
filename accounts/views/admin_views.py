from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.paginator import Paginator

from django.urls import reverse
from django.shortcuts import redirect

from bson import ObjectId
from bson.errors import InvalidId

from ..mongo import obtener_bd
from ..decoradores import requiere_roles
from ..seguridad import crear_hash_contrasena




@requiere_roles("ADMIN")
def panel_admin(request):
    bd = obtener_bd()

    seccion = request.GET.get("seccion", "usuarios").strip().lower()
    if seccion not in ["usuarios", "tickets"]:
        seccion = "usuarios"

    # ---------------- USUARIOS ----------------
    q_usuario = request.GET.get("q_usuario", "").strip()
    rol_usuario = request.GET.get("rol_usuario", "").strip().upper()
    estado_usuario = request.GET.get("estado_usuario", "").strip().upper()

    usuarios_query = {}

    if rol_usuario in ["USUARIO", "TECNICO", "ADMIN"]:
        usuarios_query["rol"] = rol_usuario

    if estado_usuario == "ACTIVO":
        usuarios_query["estado.activo"] = True
    elif estado_usuario == "INACTIVO":
        usuarios_query["estado.activo"] = False

    if q_usuario:
        usuarios_query["$or"] = [
            {"perfil.nombre": {"$regex": q_usuario, "$options": "i"}},
            {"perfil.correo": {"$regex": q_usuario, "$options": "i"}},
            {"perfil.matricula": {"$regex": q_usuario, "$options": "i"}},
        ]

    usuarios_raw = list(
        bd.usuarios.find(usuarios_query).sort("meta.creado_en", -1)
    )

    usuarios = []
    total_usuarios = 0
    total_tecnicos = 0

    for u in usuarios_raw:
        rol = u.get("rol", "USUARIO")
        activo = u.get("estado", {}).get("activo", True)
        perfil = u.get("perfil", {})
        ultimo_acceso = u.get("autenticacion", {}).get("ultimo_acceso")

        nombre = perfil.get("nombre", "Sin nombre")
        correo = perfil.get("correo")
        matricula = perfil.get("matricula")
        identificador = correo if correo else matricula if matricula else "—"

        if activo:
            total_usuarios += 1

        if rol == "TECNICO" and activo:
            total_tecnicos += 1

        partes = nombre.split()
        iniciales = ""
        for p in partes[:2]:
            if p:
                iniciales += p[0].upper()
        if not iniciales:
            iniciales = "US"

        usuarios.append({
            "id": str(u["_id"]),
            "nombre": nombre,
            "correo": correo,
            "matricula": matricula,
            "identificador": identificador,
            "rol": rol,
            "activo": activo,
            "ultimo_acceso": ultimo_acceso.strftime("%d-%b %H:%M") if ultimo_acceso else "—",
            "iniciales": iniciales,
        })

    # ---------------- CATÁLOGOS ----------------
    labs = list(bd.catalogos_laboratorios.find({"activo": True}).sort("orden", 1))
    cats = list(bd.catalogos_categorias.find({"activo": True}).sort("orden", 1))

    lab_map = {str(x["_id"]): x["nombre"] for x in labs}
    cat_map = {str(x["_id"]): x["nombre"] for x in cats}

    laboratorios = [{"id": str(x["_id"]), "nombre": x["nombre"]} for x in labs]
    categorias = [{"id": str(x["_id"]), "nombre": x["nombre"]} for x in cats]

    # ---------------- TICKETS ----------------
    q_ticket = request.GET.get("q_ticket", "").strip()
    lab_ticket = request.GET.get("lab_ticket", "").strip()
    cat_ticket = request.GET.get("cat_ticket", "").strip()
    estado_ticket = request.GET.get("estado_ticket", "").strip().upper()
    prioridad_ticket = request.GET.get("prioridad_ticket", "").strip().upper()
    tecnico_ticket = request.GET.get("tecnico_ticket", "").strip()

    tickets_query = {}

    if lab_ticket:
        try:
            tickets_query["laboratorio_id"] = ObjectId(lab_ticket)
        except InvalidId:
            pass

    if cat_ticket:
        try:
            tickets_query["categoria_id"] = ObjectId(cat_ticket)
        except InvalidId:
            pass

    if estado_ticket in ["NUEVO", "REVISION", "PROCESO", "RESUELTO", "CERRADO"]:
        tickets_query["estado"] = estado_ticket

    if prioridad_ticket in ["ALTA", "MEDIA", "BAJA"]:
        tickets_query["prioridad"] = prioridad_ticket

    if tecnico_ticket == "SIN_ASIGNAR":
        tickets_query["asignado_a"] = None
    elif tecnico_ticket:
        try:
            tickets_query["asignado_a"] = ObjectId(tecnico_ticket)
        except InvalidId:
            pass

    if q_ticket:
        tickets_query["$or"] = [
            {"folio": {"$regex": q_ticket, "$options": "i"}},
            {"codigo": {"$regex": q_ticket, "$options": "i"}},
            {"descripcion": {"$regex": q_ticket, "$options": "i"}},
        ]

    tickets_raw = list(
        bd.tickets.find(tickets_query).sort("meta.actualizado_en", -1)
    )

    todos_usuarios_raw = list(bd.usuarios.find())
    user_map = {
        str(u["_id"]): u.get("perfil", {}).get("nombre", "Sin nombre")
        for u in todos_usuarios_raw
    }

    tickets = []
    tickets_hoy = 0
    sin_resolver = 0
    hoy = timezone.localdate()

    for t in tickets_raw:
        creado_en = t.get("meta", {}).get("creado_en")
        actualizado_en = t.get("meta", {}).get("actualizado_en")
        estado = t.get("estado", "NUEVO")
        prioridad = t.get("prioridad", "MEDIA")
        asignado_a = t.get("asignado_a")

        if creado_en and creado_en.date() == hoy:
            tickets_hoy += 1

        if estado not in ["RESUELTO", "CERRADO"]:
            sin_resolver += 1

        tecnico_nombre = "Sin asignar"
        if asignado_a:
            tecnico_nombre = user_map.get(str(asignado_a), "Sin asignar")

        tickets.append({
            "id": str(t["_id"]),
            "folio": t.get("folio", "—"),
            "laboratorio_nombre": lab_map.get(str(t.get("laboratorio_id")), "—"),
            "categoria_nombre": cat_map.get(str(t.get("categoria_id")), "—"),
            "codigo": t.get("codigo", "—"),
            "descripcion": t.get("descripcion", "—"),
            "prioridad": prioridad,
            "estado": estado,
            "tecnico": tecnico_nombre,
            "tecnico_id": str(asignado_a) if asignado_a else "",
            "actualizado_en": actualizado_en.strftime("%d-%b %H:%M") if actualizado_en else "—",
            "creado_en": creado_en.strftime("%d-%b %H:%M") if creado_en else "—",
            "evidencia_url": (
                t.get("evidencias", [{}])[0].get("url")
                if t.get("evidencias") else ""
            ),
        })

    # ---------------- PAGINACIÓN ----------------
    pagina_usuarios = request.GET.get("pagina_usuarios", 1)
    paginador_usuarios = Paginator(usuarios, 10)
    usuarios_page = paginador_usuarios.get_page(pagina_usuarios)

    pagina_tickets = request.GET.get("pagina_tickets", 1)
    paginador_tickets = Paginator(tickets, 10)
    tickets_page = paginador_tickets.get_page(pagina_tickets)

    context = {
        "usuarios": usuarios_page,
        "tickets": tickets_page,
        "seccion_activa": seccion,
        "kpis": {
            "usuarios_totales": total_usuarios,
            "tecnicos": total_tecnicos,
            "tickets_hoy": tickets_hoy,
            "sin_resolver": sin_resolver,
        },
        "filtros": {
            "q_usuario": q_usuario,
            "rol_usuario": rol_usuario,
            "estado_usuario": estado_usuario,
            "q_ticket": q_ticket,
            "lab_ticket": lab_ticket,
            "cat_ticket": cat_ticket,
            "estado_ticket": estado_ticket,
            "prioridad_ticket": prioridad_ticket,
            "tecnico_ticket": tecnico_ticket,
        },
        "laboratorios_filtro": [
            {"id": str(x["_id"]), "nombre": x["nombre"]}
            for x in labs
        ],
        "categorias_filtro": [
            {"id": str(x["_id"]), "nombre": x["nombre"]}
            for x in cats
        ],
        "tecnicos_filtro": [
            {
                "id": str(u["_id"]),
                "nombre": u.get("perfil", {}).get("nombre", "Sin nombre")
            }
            for u in todos_usuarios_raw
            if u.get("rol") == "TECNICO" and u.get("estado", {}).get("activo", True)
        ],
    }

    context["laboratorios"] = laboratorios
    context["categorias"] = categorias

    return render(request, "panel_admin.html", context)


@require_POST
@requiere_roles("ADMIN")
def crear_usuario_admin(request):
    nombre = request.POST.get("nombre", "").strip()
    identificador = request.POST.get("identificador", "").strip().lower()
    rol = request.POST.get("rol", "").strip().upper()
    contrasena = request.POST.get("contrasena", "").strip()

    if not nombre or not identificador or not rol or not contrasena:
        messages.error(request, "Faltan campos obligatorios.")
        return redirect("panel_admin")

    if rol not in ["USUARIO", "TECNICO", "ADMIN"]:
        messages.error(request, "Rol inválido.")
        return redirect("panel_admin")

    es_correo = "@" in identificador
    bd = obtener_bd()

    # Validar duplicados
    filtro_existente = {"perfil.correo": identificador} if es_correo else {"perfil.matricula": identificador}
    if bd.usuarios.find_one(filtro_existente):
        messages.error(request, "Ya existe un usuario con ese correo/matrícula.")
        return redirect("panel_admin")

    ahora = timezone.now()
    doc = {
        "rol": rol,
        "perfil": {
            "nombre": nombre,
            "correo": identificador if es_correo else None,
            "matricula": None if es_correo else identificador,
        },
        "autenticacion": {
            "contrasena_hash": crear_hash_contrasena(contrasena),
            "ultimo_acceso": None,
        },
        "estado": {"activo": True},
        "meta": {"creado_en": ahora, "actualizado_en": ahora},
    }

    bd.usuarios.insert_one(doc)
    messages.success(request, "Usuario creado correctamente.")
    return redirect("panel_admin")

@require_POST
@requiere_roles("ADMIN")
def editar_usuario_admin(request, usuario_id):
    bd = obtener_bd()

    try:
        oid = ObjectId(usuario_id)
    except InvalidId:
        messages.error(request, "ID de usuario inválido.")
        return redirect("panel_admin")

    usuario = bd.usuarios.find_one({"_id": oid})
    if not usuario:
        messages.error(request, "Usuario no encontrado.")
        return redirect("panel_admin")

    nombre = request.POST.get("nombre", "").strip()
    identificador = request.POST.get("identificador", "").strip().lower()
    rol = request.POST.get("rol", "").strip().upper()

    if not nombre or not identificador or not rol:
        messages.error(request, "Todos los campos son obligatorios.")
        return redirect("panel_admin")

    if rol not in ["USUARIO", "TECNICO", "ADMIN"]:
        messages.error(request, "Rol inválido.")
        return redirect("panel_admin")

    es_correo = "@" in identificador

    if es_correo and not identificador.endswith("@utcj.edu.mx"):
        messages.error(request, "Solo se permiten correos institucionales UTCJ.")
        return redirect("panel_admin")

    filtro_existente = {"_id": {"$ne": oid}}
    if es_correo:
        filtro_existente["perfil.correo"] = identificador
    else:
        filtro_existente["perfil.matricula"] = identificador

    if bd.usuarios.find_one(filtro_existente):
        messages.error(request, "Ya existe otro usuario con ese correo/matrícula.")
        return redirect("panel_admin")

    bd.usuarios.update_one(


        {"_id": oid},
        {
            "$set": {
                "perfil.nombre": nombre,
                "perfil.correo": identificador if es_correo else None,
                "perfil.matricula": None if es_correo else identificador,
                "rol": rol,
                "meta.actualizado_en": timezone.now(),
            }
        }
    )

    messages.success(request, "Usuario actualizado correctamente.")
    return redirect("panel_admin")

@require_POST
@requiere_roles("ADMIN")
def cambiar_password_admin(request, usuario_id):
    bd = obtener_bd()

    try:
        oid = ObjectId(usuario_id)
    except InvalidId:
        messages.error(request, "ID de usuario inválido.")
        return redirect("panel_admin")

    usuario = bd.usuarios.find_one({"_id": oid})
    if not usuario:
        messages.error(request, "Usuario no encontrado.")
        return redirect("panel_admin")

    nueva = request.POST.get("nueva_contrasena", "").strip()
    confirmar = request.POST.get("confirmar_contrasena", "").strip()

    if not nueva or not confirmar:
        messages.error(request, "Debes llenar ambos campos.")
        return redirect("panel_admin")

    if nueva != confirmar:
        messages.error(request, "Las contraseñas no coinciden.")
        return redirect("panel_admin")

    if len(nueva) < 6:
        messages.error(request, "La contraseña debe tener al menos 6 caracteres.")
        return redirect("panel_admin")

    bd.usuarios.update_one(
        {"_id": oid},
        {
            "$set": {
                "autenticacion.contrasena_hash": crear_hash_contrasena(nueva),
                "meta.actualizado_en": timezone.now(),
            }
        }
    )

    messages.success(request, "Contraseña actualizada correctamente.")
    return redirect("panel_admin")

@require_POST
@requiere_roles("ADMIN")
def eliminar_usuario_admin(request, usuario_id):
    bd = obtener_bd()

    try:
        oid = ObjectId(usuario_id)
    except InvalidId:
        messages.error(request, "ID de usuario inválido.")
        return redirect("panel_admin")

    usuario = bd.usuarios.find_one({"_id": oid})
    if not usuario:
        messages.error(request, "Usuario no encontrado.")
        return redirect("panel_admin")

    if request.session.get("usuario_id") == usuario_id:
        messages.error(request, "No puedes borrar tu propia cuenta.")
        return redirect("panel_admin")

    if usuario.get("estado", {}).get("activo", True):
        messages.error(request, "Primero debes desactivar al usuario antes de borrarlo.")
        return redirect("panel_admin")

    bd.usuarios.delete_one({"_id": oid})

    messages.success(request, "Usuario eliminado correctamente.")
    return redirect("panel_admin")

@require_POST
@requiere_roles("ADMIN")
def activar_usuario_admin(request, usuario_id):
    bd = obtener_bd()

    try:
        oid = ObjectId(usuario_id)
    except InvalidId:
        messages.error(request, "ID de usuario inválido.")
        return redirect("panel_admin")

    usuario = bd.usuarios.find_one({"_id": oid})
    if not usuario:
        messages.error(request, "Usuario no encontrado.")
        return redirect("panel_admin")

    bd.usuarios.update_one(
        {"_id": oid},
        {
            "$set": {
                "estado.activo": True,
                "meta.actualizado_en": timezone.now(),
            }
        }
    )

    messages.success(request, "Usuario activado correctamente.")
    return redirect("panel_admin")

@require_POST
@requiere_roles("ADMIN")
def desactivar_usuario_admin(request, usuario_id):
    bd = obtener_bd()

    try:
        oid = ObjectId(usuario_id)
    except InvalidId:
        messages.error(request, "ID de usuario inválido.")
        return redirect("panel_admin")

    usuario = bd.usuarios.find_one({"_id": oid})
    if not usuario:
        messages.error(request, "Usuario no encontrado.")
        return redirect("panel_admin")

    if request.session.get("usuario_id") == usuario_id:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect("panel_admin")

    bd.usuarios.update_one(
        {"_id": oid},
        {
            "$set": {
                "estado.activo": False,
                "meta.actualizado_en": timezone.now(),
            }
        }
    )

    messages.success(request, "Usuario desactivado correctamente.")
    return redirect("panel_admin")


@require_POST
@requiere_roles("ADMIN")
def asignar_ticket_admin(request, ticket_id):
    bd = obtener_bd()

    try:
        ticket_oid = ObjectId(ticket_id)
    except InvalidId:
        messages.error(request, "ID de ticket inválido.")
        return redirect(f"{reverse('panel_admin')}?seccion=tickets")

    tecnico_id = request.POST.get("tecnico_id", "").strip()

    if not tecnico_id:
        messages.error(request, "Debes seleccionar un técnico.")
        return redirect(f"{reverse('panel_admin')}?seccion=tickets")

    try:
        tecnico_oid = ObjectId(tecnico_id)
    except InvalidId:
        messages.error(request, "ID de técnico inválido.")
        return redirect(f"{reverse('panel_admin')}?seccion=tickets")

    ticket = bd.tickets.find_one({"_id": ticket_oid})
    if not ticket:
        messages.error(request, "Ticket no encontrado.")
        return redirect(f"{reverse('panel_admin')}?seccion=tickets")

    tecnico = bd.usuarios.find_one({
        "_id": tecnico_oid,
        "rol": "TECNICO",
        "estado.activo": True
    })

    if not tecnico:
        messages.error(request, "El técnico seleccionado no es válido.")
        return redirect(f"{reverse('panel_admin')}?seccion=tickets")

    ahora = timezone.now()

    nuevo_estado = ticket.get("estado", "NUEVO")
    if nuevo_estado == "NUEVO":
        nuevo_estado = "REVISION"

    bd.tickets.update_one(
        {"_id": ticket_oid},
        {
            "$set": {
                "asignado_a": tecnico_oid,
                "estado": nuevo_estado,
                "meta.actualizado_en": ahora
            },
            "$push": {
                "historial": {
                    "estado": nuevo_estado,
                    "por": ObjectId(request.session.get("usuario_id")),
                    "fecha": ahora,
                    "nota": f"Ticket asignado a {tecnico.get('perfil', {}).get('nombre', 'Técnico')}"
                }
            }
        }
    )

    messages.success(request, "Ticket asignado correctamente.")
    return redirect(f"{reverse('panel_admin')}?seccion=tickets")