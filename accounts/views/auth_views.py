from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone

from ..mongo import obtener_bd
from ..seguridad import verificar_contrasena

def vista_login(request):
    # GET
    if request.method == "GET":
        if request.session.get("usuario_id"):
            rol = request.session.get("rol", "USUARIO")
            if rol == "ADMIN":
                return redirect("panel_admin")
            elif rol == "TECNICO":
                return redirect("tecnico")
            return redirect("usuario")

        return render(request, "login.html")

    # POST
    correo = request.POST.get("correo", "").strip().lower()
    contrasena = request.POST.get("password", "").strip()
    recordar = request.POST.get("recordar")

    if not correo or not contrasena:
        messages.error(request, "Debes ingresar tu correo institucional y tu contraseña.")
        return render(request, "login.html")

    # Validación: solo correos UTCJ
    if not correo.endswith("@utcj.edu.mx"):
        messages.error(request, "Acceso exclusivo para personal UTCJ. Usa tu correo institucional.")
        return render(request, "login.html")

    bd = obtener_bd()

    usuario = bd.usuarios.find_one({
        "perfil.correo": correo
    })

    if not usuario:
        messages.error(request, "Correo no encontrado.")
        return render(request, "login.html")

    if not usuario.get("estado", {}).get("activo", True):
        messages.error(request, "Tu cuenta está desactivada. Contacta al administrador.")
        return render(request, "login.html")

    hash_guardado = usuario.get("autenticacion", {}).get("contrasena_hash")
    if not hash_guardado or not verificar_contrasena(hash_guardado, contrasena):
        messages.error(request, "Contraseña incorrecta.")
        return render(request, "login.html")

    # Seguridad: renovar identificador de sesión
    request.session.cycle_key()

    # Guardar sesión
    request.session["usuario_id"] = str(usuario["_id"])
    request.session["rol"] = usuario.get("rol", "USUARIO")

    # Mantener sesión
    if recordar:
        request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    else:
        request.session.set_expiry(0)

    # Actualizar último acceso
    bd.usuarios.update_one(
        {"_id": usuario["_id"]},
        {
            "$set": {
                "autenticacion.ultimo_acceso": timezone.now(),
                "meta.actualizado_en": timezone.now(),
            }
        }
    )

    # Redirección por rol
    rol = request.session["rol"]
    if rol == "ADMIN":
        return redirect("panel_admin")
    elif rol == "TECNICO":
        return redirect("tecnico")
    return redirect("usuario")


def vista_logout(request):
    request.session.flush()
    return redirect("login")