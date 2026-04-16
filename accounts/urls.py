from django.urls import path
from . import views
from .views import admin_views

urlpatterns = [
    path("", views.vista_login, name="login"),
    path("login/", views.vista_login, name="login"),
    path("logout/", views.vista_logout, name="logout"),

    path("usuario/", views.panel_usuario, name="usuario"),
    path("usuario/crear-ticket/", views.crear_ticket, name="crear_ticket"),

    # ================= TECNICO =================
    path("tecnico/", views.panel_tecnico, name="tecnico"),

    # RF-12 Tomar ticket
    path("tecnico/ticket/<str:ticket_id>/tomar/", views.tomar_ticket, name="tomar_ticket"),

    # RF-13-16 Gestión
    path("tecnico/ticket/<str:ticket_id>/", views.ticket_detalle_tecnico, name="ticket_detalle_tecnico"),
    path("tecnico/ticket/<str:ticket_id>/gestionar/", views.ticket_gestionar, name="ticket_gestionar"),



    path("administrador/", views.panel_admin, name="panel_admin"),
    path("administrador/usuarios/crear/", views.crear_usuario_admin, name="crear_usuario_admin"),
    path("administrador/usuarios/<str:usuario_id>/editar/", views.editar_usuario_admin, name="editar_usuario_admin"),
    path("administrador/usuarios/<str:usuario_id>/password/", views.cambiar_password_admin, name="cambiar_password_admin"),
    path("administrador/usuarios/<str:usuario_id>/activar/", views.activar_usuario_admin, name="activar_usuario_admin"),
    path("administrador/usuarios/<str:usuario_id>/desactivar/", views.desactivar_usuario_admin, name="desactivar_usuario_admin"),
    path("administrador/usuarios/<str:usuario_id>/eliminar/", views.eliminar_usuario_admin, name="eliminar_usuario_admin"),
    path("administrador/tickets/<str:ticket_id>/asignar/",views.asignar_ticket_admin, name="asignar_ticket_admin"),



    path("administrador/reportes/html/", views.reporte_admin_html, name="reporte_admin_html"),
    path("administrador/reportes/pdf/", views.reporte_admin_pdf, name="reporte_admin_pdf"),
    path("administrador/reportes/generar/", views.generar_reporte_admin_guardado,name="generar_reporte_admin_guardado"),


    path("administrador/reportes/<str:reporte_id>/enviar/",admin_views.enviar_reporte_guardado_admin, name="enviar_reporte_guardado_admin",),
]


