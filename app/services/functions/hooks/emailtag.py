import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.util.database import LocalStorage
import json
import logging

logging.basicConfig(level=logging.DEBUG)

def Run(call, config):
    """
    Friendly Name: Email Tagger

    Description:
    Este hook envía un correo electrónico una vez que la llamada ha finalizado. Se puede etiquetar la llamada y luego enviar un correo con los detalles.

    Hook Type: POST_CALL

    Logo URL: https://example.com/logo.png
    """

    logging.debug(f"Objeto call: {call}")

    # Configuración del servidor SMTP
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_username = "dederico@gmail.com"  # Cambia a tu dirección de correo
    smtp_password = "beas ajht qlgb eshd"  # Cambia a tu contraseña de correo
    email_to = "dederico@gmail.com,soporte@cybersecuritydemexico.com.mx,banxico@cybersecuritydemexico.com.mx,soporte_uem@cybersecuritydemexico.com.mx,asistencia@cybersecuritydemexico.com.mx"  # Cambia a tus direcciones

    # Lógica para etiquetar la llamada
    if call.callStatus == "AMD":
        call.callStatus = "BUZON"
    elif call.callDuration < 60:
        call.callStatus = "RECOVER"
    elif call.callScript:
        chat = json.loads(call.callScript)
        chat = [m["dialog"] for m in chat if m['role'] == "CUSTOMER"]

        schedule_keywords = {"schedule", "call", "reschedule", "time", "date", "afternoon", "tomorrow"}

        # Aquí podrías añadir lógica similar a isAnnoying o keyword_matching si fuera necesario

        # Si se encuentra un criterio específico, se marca con la etiqueta "AGENDA"
        if any(keyword in " ".join(chat) for keyword in schedule_keywords):
            call.callStatus = "AGENDA"

    # Enviar correo electrónico si la llamada tiene cambios
    if call.isDirty:
        # Crear el mensaje de correo
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = email_to
        msg['Subject'] = f"Reporte de Llamada: {call.callStatus}"

        # Cuerpo del correo
        email_body = f"Detalles de la llamada:\n\nID de Llamada: {call.callID}\nEstado: {call.callStatus}\nDuración: {call.callDuration} segundos\n"
        msg.attach(MIMEText(email_body, 'plain'))

        # Conectar al servidor SMTP y enviar el correo
        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()  # Habilitar TLS
            server.login(smtp_username, smtp_password)  # Iniciar sesión en el servidor SMTP
            server.send_message(msg)  # Enviar el mensaje
        except Exception as e:
            print(f"Error al enviar el correo: {e}")
        finally:
            server.quit()  # Cerrar la conexión con el servidor

        # Guardar la llamada etiquetada en la base de datos
        ls = LocalStorage()
        ls.Update(call)
        return True

    return False
