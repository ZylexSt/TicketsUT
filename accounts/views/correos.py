from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives


def _obtener_correo(usuario):
    return (usuario.get("perfil", {}).get("correo") or "").strip().lower()


def _nombre_usuario(usuario, defecto="Usuario"):
    return usuario.get("perfil", {}).get("nombre", defecto)


def _datos_ticket(ticket):
    return {
        "folio": ticket.get("folio", "Sin folio"),
        "codigo": ticket.get("codigo", "Sin código"),
        "descripcion": ticket.get("descripcion", "Sin descripción"),
        "prioridad": ticket.get("prioridad", "MEDIA"),
        "estado": ticket.get("estado", "NUEVO"),
    }


def enviar_correo_ticket_asignado(tecnico, ticket, asignado_por="Administrador"):
    correo = _obtener_correo(tecnico)
    if not correo:
        return False, "El técnico no tiene correo registrado."

    nombre_tecnico = _nombre_usuario(tecnico, "Técnico")
    datos = _datos_ticket(ticket)

    asunto = f"[Tickets UTCJ] Ticket asignado: {datos['folio']}"

    texto = (
        f"Hola {nombre_tecnico},\n\n"
        f"Se te ha asignado un ticket.\n\n"
        f"Folio: {datos['folio']}\n"
        f"Código: {datos['codigo']}\n"
        f"Descripción: {datos['descripcion']}\n"
        f"Prioridad: {datos['prioridad']}\n"
        f"Estado actual: {datos['estado']}\n"
        f"Asignado por: {asignado_por}\n\n"
        "Ingresa al sistema para revisarlo.\n\n"
        "Sistema de Tickets UTCJ"
    )

    html = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.5;">
        <h2>Nuevo ticket asignado</h2>
        <p>Hola <strong>{nombre_tecnico}</strong>,</p>
        <p>Se te ha asignado un ticket en el sistema.</p>

        <ul>
            <li><strong>Folio:</strong> {datos['folio']}</li>
            <li><strong>Código:</strong> {datos['codigo']}</li>
            <li><strong>Descripción:</strong> {datos['descripcion']}</li>
            <li><strong>Prioridad:</strong> {datos['prioridad']}</li>
            <li><strong>Estado actual:</strong> {datos['estado']}</li>
            <li><strong>Asignado por:</strong> {asignado_por}</li>
        </ul>

        <p>Ingresa al sistema para revisarlo.</p>
        <p><strong>Sistema de Tickets UTCJ</strong></p>
    </div>
    """

    mensaje = EmailMultiAlternatives(
        subject=asunto,
        body=texto,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[correo],
    )
    mensaje.attach_alternative(html, "text/html")
    mensaje.send(fail_silently=False)

    return True, None


def enviar_correo_ticket_tomado(tecnico, ticket):
    correo = _obtener_correo(tecnico)
    if not correo:
        return False, "El técnico no tiene correo registrado."

    nombre_tecnico = _nombre_usuario(tecnico, "Técnico")
    datos = _datos_ticket(ticket)

    asunto = f"[Tickets UTCJ] Confirmación de ticket tomado: {datos['folio']}"

    texto = (
        f"Hola {nombre_tecnico},\n\n"
        f"Has tomado un ticket correctamente.\n\n"
        f"Folio: {datos['folio']}\n"
        f"Código: {datos['codigo']}\n"
        f"Descripción: {datos['descripcion']}\n"
        f"Prioridad: {datos['prioridad']}\n"
        f"Estado actual: {datos['estado']}\n\n"
        "Sistema de Tickets UTCJ"
    )

    html = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.5;">
        <h2>Ticket tomado correctamente</h2>
        <p>Hola <strong>{nombre_tecnico}</strong>,</p>
        <p>Has tomado un ticket correctamente.</p>

        <ul>
            <li><strong>Folio:</strong> {datos['folio']}</li>
            <li><strong>Código:</strong> {datos['codigo']}</li>
            <li><strong>Descripción:</strong> {datos['descripcion']}</li>
            <li><strong>Prioridad:</strong> {datos['prioridad']}</li>
            <li><strong>Estado actual:</strong> {datos['estado']}</li>
        </ul>

        <p><strong>Sistema de Tickets UTCJ</strong></p>
    </div>
    """

    mensaje = EmailMultiAlternatives(
        subject=asunto,
        body=texto,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[correo],
    )
    mensaje.attach_alternative(html, "text/html")
    mensaje.send(fail_silently=False)

    return True, None


def enviar_reporte_admin_por_correo(destinatarios, ruta_pdf, reporte, generado_por="Administrador"):
    destinatarios_limpios = [
        correo.strip().lower()
        for correo in destinatarios
        if correo and correo.strip()
    ]

    if not destinatarios_limpios:
        return False, "No hay destinatarios válidos."

    ruta_pdf = Path(ruta_pdf)
    if not ruta_pdf.exists():
        return False, "No se encontró el PDF del reporte."

    fecha_inicio = reporte.get("fecha_inicio", "—")
    fecha_fin = reporte.get("fecha_fin", "—")
    resumen = reporte.get("resumen", {})

    asunto = f"[Tickets UTCJ] Reporte administrativo {fecha_inicio} a {fecha_fin}"

    texto = (
        f"Hola,\n\n"
        f"Se adjunta el reporte administrativo generado por {generado_por}.\n\n"
        f"Periodo: {fecha_inicio} a {fecha_fin}\n"
        f"Usuarios creados: {resumen.get('usuarios_creados', 0)}\n"
        f"Accesos totales: {resumen.get('accesos_totales', 0)}\n"
        f"Tickets creados: {resumen.get('tickets_creados', 0)}\n"
        f"Tickets cerrados: {resumen.get('tickets_cerrados', 0)}\n\n"
        f"Archivo adjunto: {ruta_pdf.name}\n\n"
        "Sistema de Tickets UTCJ"
    )

    mensaje = EmailMessage(
        subject=asunto,
        body=texto,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=destinatarios_limpios,
    )
    mensaje.attach_file(str(ruta_pdf))
    mensaje.send(fail_silently=False)

    return True, None