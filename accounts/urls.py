from django.urls import path
from . import views

urlpatterns = [
    path("", views.vista_login, name="login"),
    path("login/", views.vista_login, name="login"),
    path("logout/", views.vista_logout, name="logout"),

    path("usuario/", views.panel_usuario, name="usuario"),
    path("tecnico/", views.panel_tecnico, name="tecnico"),
    path("administrador/", views.panel_admin, name="panel_admin"),
    path("administrador/usuarios/crear/", views.crear_usuario_admin, name="crear_usuario_admin"),
    path("usuario/tickets/crear/", views.crear_ticket_usuario, name="crear_ticket_usuario"),
    path("administrador/usuarios/<str:usuario_id>/activar/", views.activar_usuario_admin, name="activar_usuario_admin"),
path("administrador/usuarios/<str:usuario_id>/desactivar/", views.desactivar_usuario_admin, name="desactivar_usuario_admin"),
]