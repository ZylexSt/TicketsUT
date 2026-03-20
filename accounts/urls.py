from django.urls import path
from . import views

urlpatterns = [
    path("", views.vista_login, name="login"),
    path("login/", views.vista_login, name="login"),
    path("logout/", views.vista_logout, name="logout"),

    path("usuario/", views.panel_usuario, name="usuario"),
    path("usuario/crear-ticket/", views.crear_ticket, name="crear_ticket"),

    path("tecnico/", views.panel_tecnico, name="tecnico"),

    path("administrador/", views.panel_admin, name="panel_admin"),
    path("administrador/usuarios/crear/", views.crear_usuario_admin, name="crear_usuario_admin"),
    path("administrador/usuarios/<str:usuario_id>/editar/", views.editar_usuario_admin, name="editar_usuario_admin"),
    path("administrador/usuarios/<str:usuario_id>/password/", views.cambiar_password_admin, name="cambiar_password_admin"),
    path("administrador/usuarios/<str:usuario_id>/activar/", views.activar_usuario_admin, name="activar_usuario_admin"),
    path("administrador/usuarios/<str:usuario_id>/desactivar/", views.desactivar_usuario_admin, name="desactivar_usuario_admin"),
    path("administrador/usuarios/<str:usuario_id>/eliminar/", views.eliminar_usuario_admin, name="eliminar_usuario_admin"),
    path("administrador/tickets/<str:ticket_id>/asignar/",views.asignar_ticket_admin, name="asignar_ticket_admin"),
]