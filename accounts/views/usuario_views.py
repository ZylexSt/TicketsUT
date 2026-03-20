from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.urls import reverse
from django.shortcuts import redirect

from bson import ObjectId

from ..mongo import obtener_bd, siguiente_folio_ticket
from ..decoradores import requiere_roles

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
                "codigo": t.get("codigo", ""),
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
def crear_ticket(request):
    bd = obtener_bd()

    usuario_id = request.session.get("usuario_id")
    rol = request.session.get("rol")

    laboratorio_id = request.POST.get("laboratorio_id")
    categoria_id = request.POST.get("categoria_id")
    codigo = (request.POST.get("codigo") or "").strip()
    prioridad = (request.POST.get("prioridad") or "").strip().upper()
    descripcion = (request.POST.get("descripcion") or "").strip()

    def redireccion_final():
        if rol == "ADMIN":
            return redirect(f"{reverse('panel_admin')}?seccion=tickets")
        elif rol == "TECNICO":
            return redirect("tecnico")
        return redirect("usuario")

    if not usuario_id:
        messages.error(request, "Tu sesión no es válida.")
        return redirect("login")

    if not laboratorio_id or not categoria_id or not codigo or not descripcion:
        messages.error(request, "Completa todos los campos obligatorios del ticket.")
        return redireccion_final()

    if prioridad not in ["BAJA", "MEDIA", "ALTA"]:
        prioridad = "MEDIA"

    codigo_normalizado = codigo.upper().replace(" ", "")

    try:
        usuario_oid = ObjectId(usuario_id)
        laboratorio_oid = ObjectId(laboratorio_id)
        categoria_oid = ObjectId(categoria_id)
    except InvalidId:
        messages.error(request, "Los datos enviados no son válidos.")
        return redireccion_final()

    # Bloquear tickets duplicados abiertos para el mismo código
    ticket_existente = bd.tickets.find_one({
        "codigo_normalizado": codigo_normalizado,
        "estado": {"$in": ["NUEVO", "REVISION", "PROCESO"]}
    })

    if ticket_existente:
        messages.warning(
            request,
            f"Ya existe un ticket abierto para el código {codigo_normalizado}."
        )
        return redireccion_final()

    evidencia_url = None

    if "evidencia" in request.FILES and request.FILES["evidencia"]:
        archivo = request.FILES["evidencia"]

        fs = FileSystemStorage(location=settings.MEDIA_ROOT / "tickets")
        nombre = fs.save(archivo.name, archivo)
        evidencia_url = f"/media/tickets/{nombre}"

    try:
        folio = siguiente_folio_ticket()

        ticket = {
            "folio": folio,
            "creado_por": usuario_oid,
            "laboratorio_id": laboratorio_oid,
            "categoria_id": categoria_oid,
            "codigo": codigo,
            "codigo_normalizado": codigo_normalizado,
            "descripcion": descripcion,
            "prioridad": prioridad,
            "estado": "NUEVO",
            "historial": [
                {
                    "estado": "NUEVO",
                    "por": usuario_oid,
                    "fecha": timezone.now(),
                    "nota": "Ticket creado"
                }
            ],
            "evidencias": [
                {
                    "url": evidencia_url,
                    "fecha": timezone.now(),
                    "subido_por": usuario_oid
                }
            ] if evidencia_url else [],
            "meta": {
                "creado_en": timezone.now(),
                "actualizado_en": timezone.now()
            }
        }

        codigo_normalizado = codigo.upper().replace(" ", "")

        ticket_existente = bd.tickets.find_one({
            "codigo_normalizado": codigo_normalizado,
            "estado": {"$in": ["NUEVO", "REVISION", "PROCESO"]}
        })

        if ticket_existente:
            messages.warning(
                request,
                f"Ya existe un ticket abierto para el código {codigo_normalizado}."
            )

            if rol == "ADMIN":
                return redirect(f"{reverse('panel_admin')}?seccion=tickets")
            elif rol == "TECNICO":
                return redirect("tecnico")
            return redirect("usuario")

        bd.tickets.insert_one(ticket)
        messages.success(request, f"Ticket {folio} creado correctamente.")

    except Exception:
        messages.error(request, "No se pudo crear el ticket. Verifica los datos enviados.")

    return redireccion_final()