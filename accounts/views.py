from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from django.contrib import messages
from bson.errors import InvalidId
from bson import ObjectId
from django.utils import timezone

import os

from .mongo import obtener_bd
from .mongo import siguiente_folio_ticket
from .decoradores import requiere_roles
from .seguridad import verificar_contrasena, crear_hash_contrasena


def vista_login(request):
    # GET
    if request.method == "GET":
        # Si ya hay sesión, manda directo al panel
        if request.session.get("usuario_id"):
            rol = request.session.get("rol", "USUARIO")
            if rol == "ADMIN":
                return redirect("panel_admin")
            elif rol == "TECNICO":
                return redirect("tecnico")
            return redirect("usuario")

        return render(request, "login.html")

    # POST
    identificador = request.POST.get("correo", "").strip().lower()
    contrasena = request.POST.get("password", "").strip()

    if not identificador or not contrasena:
        messages.error(request, "Debes ingresar correo y contraseña.")
        return render(request, "login.html")

    bd = obtener_bd()

    usuario = bd.usuarios.find_one({
        "$or": [
            {"perfil.correo": identificador},
            {"perfil.matricula": identificador},
        ]
    })

    if not usuario:
        messages.error(request, "Credenciales inválidas.")
        return render(request, "login.html")

    if not usuario.get("estado", {}).get("activo", True):
        messages.error(request, "Cuenta desactivada.")
        return render(request, "login.html")

    hash_guardado = usuario.get("autenticacion", {}).get("contrasena_hash")
    if not hash_guardado or not verificar_contrasena(hash_guardado, contrasena):
        messages.error(request, "Credenciales inválidas.")
        return render(request, "login.html")

    # Guardar sesión
    request.session["usuario_id"] = str(usuario["_id"])
    request.session["rol"] = usuario.get("rol", "USUARIO")

    # Actualizar último acceso
    bd.usuarios.update_one(
        {"_id": usuario["_id"]},
        {"$set": {"autenticacion.ultimo_acceso": timezone.now()}}
    )

    # Redirección por rol
    rol = request.session["rol"]
    if rol == "ADMIN":
        return redirect("panel_admin")
    elif rol == "TECNICO":
        return redirect("tecnico")
    return redirect("usuario")


@requiere_roles("USUARIO", "TECNICO", "ADMIN")
def panel_usuario(request):
    bd = obtener_bd()

    # 1) Catálogos (activos, ordenados)
    labs = list(bd.catalogos_laboratorios.find({"activo": True}).sort("orden", 1))
    cats = list(bd.catalogos_categorias.find({"activo": True}).sort("orden", 1))

    laboratorios = [{"id": str(x["_id"]), "nombre": x["nombre"]} for x in labs]
    categorias = [{"id": str(x["_id"]), "nombre": x["nombre"]} for x in cats]

    # 2) Mis tickets (si aún no tienes colección tickets, esto regresará vacío)
    tickets = []
    usuario_id = request.session.get("usuario_id")
    if usuario_id:
        tickets_raw = list(
            bd.tickets.find({"creado_por": ObjectId(usuario_id)}).sort("meta.actualizado_en", -1)
        )

        # mapas para mostrar nombre desde id
        lab_map = {str(x["_id"]): x["nombre"] for x in labs}
        cat_map = {str(x["_id"]): x["nombre"] for x in cats}

        for t in tickets_raw:
            actualizado = t.get("meta", {}).get("actualizado_en")
            tickets.append({
                "folio": t.get("folio", ""),
                "laboratorio_nombre": lab_map.get(str(t.get("laboratorio_id")), "—"),
                "categoria_nombre": cat_map.get(str(t.get("categoria_id")), "—"),
                "activo": t.get("activo", ""),
                "descripcion": t.get("descripcion", ""),
                "prioridad": t.get("prioridad", "MEDIA"),
                "estado": t.get("estado", "NUEVO"),
                "actualizado_en": actualizado.strftime("%d-%b %H:%M") if actualizado else "—",
            })

    return render(request, "usuario.html", {
        "laboratorios": laboratorios,
        "categorias": categorias,
        "tickets": tickets
    })

@require_POST
@requiere_roles("USUARIO", "TECNICO", "ADMIN")
def crear_ticket_usuario(request):
    bd = obtener_bd()

    usuario_id = request.session.get("usuario_id")

    laboratorio_id = request.POST.get("laboratorio_id")
    categoria_id = request.POST.get("categoria_id")
    activo = request.POST.get("activo")
    prioridad = request.POST.get("prioridad")
    descripcion = request.POST.get("descripcion")

    evidencia_url = None

    if "evidencia" in request.FILES:
        archivo = request.FILES["evidencia"]

        fs = FileSystemStorage(
            location=settings.MEDIA_ROOT / "tickets"
        )

        nombre = fs.save(archivo.name, archivo)

        evidencia_url = f"/media/tickets/{nombre}"

    folio = siguiente_folio_ticket()

    ticket = {
        "folio": folio,
        "creado_por": ObjectId(usuario_id),

        "laboratorio_id": ObjectId(laboratorio_id),
        "categoria_id": ObjectId(categoria_id),

        "activo": activo,
        "descripcion": descripcion,
        "prioridad": prioridad,

        "estado": "NUEVO",

        "historial": [
            {
                "estado": "NUEVO",
                "por": ObjectId(usuario_id),
                "fecha": timezone.now(),
                "nota": "Ticket creado"
            }
        ],

        "evidencias": [
            {
                "url": evidencia_url,
                "fecha": timezone.now(),
                "subido_por": ObjectId(usuario_id)
            }
        ] if evidencia_url else [],

        "meta": {
            "creado_en": timezone.now(),
            "actualizado_en": timezone.now()
        }
    }

    bd.tickets.insert_one(ticket)
    messages.success(request, f"Ticket {folio} creado correctamente.")
    return redirect("usuario")

@requiere_roles("TECNICO", "ADMIN")
def panel_tecnico(request):
    return render(request, "tecnico.html")


@requiere_roles("ADMIN")
def panel_admin(request):
    bd = obtener_bd()

    # USUARIOS
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
            "identificador": identificador,
            "rol": rol,
            "activo": activo,
            "ultimo_acceso": ultimo_acceso.strftime("%d-%b %H:%M") if ultimo_acceso else "—",
            "iniciales": iniciales,
        })

    # CATÁLOGOS
    labs = list(bd.catalogos_laboratorios.find({"activo": True}))
    cats = list(bd.catalogos_categorias.find({"activo": True}))

    lab_map = {str(x["_id"]): x["nombre"] for x in labs}
    cat_map = {str(x["_id"]): x["nombre"] for x in cats}

    # TICKETS
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
            {"activo": {"$regex": q_ticket, "$options": "i"}},
            {"descripcion": {"$regex": q_ticket, "$options": "i"}},
        ]

    tickets_raw = list(
        bd.tickets.find(tickets_query).sort("meta.actualizado_en", -1)
    )

    # mapa de usuarios para mostrar nombre corto del técnico
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
            "activo": t.get("activo", "—"),
            "descripcion": t.get("descripcion", "—"),
            "prioridad": prioridad,
            "estado": estado,
            "tecnico": tecnico_nombre,
            "actualizado_en": actualizado_en.strftime("%d-%b %H:%M") if actualizado_en else "—",
        })

        context = {
            "usuarios": usuarios,
            "tickets": tickets,
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
def activar_usuario_admin(request, usuario_id):
    bd = obtener_bd()

    try:
        oid = ObjectId(usuario_id)
    except InvalidId:
        messages.error(request, "ID de usuario inválido.")
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

    # opcional: evitar desactivar al propio admin logueado
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


def vista_logout(request):
    request.session.flush()
    return redirect("login")