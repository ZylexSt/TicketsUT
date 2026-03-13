from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone

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


