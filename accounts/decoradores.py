from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden


def requiere_sesion(vista):
    @wraps(vista)
    def _envoltura(request, *args, **kwargs):
        if not request.session.get("usuario_id"):
            return redirect("login")
        return vista(request, *args, **kwargs)
    return _envoltura


def requiere_roles(*roles_permitidos):
    def _decorador(vista):
        @wraps(vista)
        def _envoltura(request, *args, **kwargs):
            if not request.session.get("usuario_id"):
                return redirect("login")

            rol = request.session.get("rol", "USUARIO")
            if rol not in roles_permitidos:
                # opción 1: 403
                return HttpResponseForbidden("No tienes permisos para acceder a esta sección.")
            return vista(request, *args, **kwargs)
        return _envoltura
    return _decorador