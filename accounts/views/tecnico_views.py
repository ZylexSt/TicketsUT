from django.shortcuts import render

from ..decoradores import requiere_roles

@requiere_roles("TECNICO", "ADMIN")
def panel_tecnico(request):
    return render(request, "tecnico.html")
