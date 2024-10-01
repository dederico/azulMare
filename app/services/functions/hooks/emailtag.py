import smtplib
import openai
from app.util.logger import logger
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.util.database import LocalStorage
import json

async def Analyze(call, config):
    try:
        llm = openai.AsyncClient()
        messages = [
            {
                "role": "system",
                "content": """Analyze the conversation between customer and support engineer,
                and generate the JSON object based on following template
                {
                    "title": "Short Issue Title",
                    "description": "summary of issue disscused in conversation"
                }
                """,
            },
            {
                "role": "user",
                "content": call.callScript,
            },
        ]

        response = await llm.chat.completions.create(
            model=config.get("model", "gpt-4-0125-preview"),
            temperature=0.1,
            messages=messages,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except:
        return False

def send_ticket_email(data: str):
    """Envía un correo electrónico con un mensaje fijo de ticket generado.
    
    Args:
        email_to (string): Dirección de correo electrónico del destinatario.
        
    Returns:
        string: Mensaje de confirmación sobre el envío del correo.
    """
    # Configuración del servidor SMTP
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_username = "dederico@gmail.com"  # Cambia a tu dirección de correo
    smtp_password = "beas ajht qlgb eshd"  # Cambia a tu contraseña de correo
    email_to = "dederico@gmail.com,soporte@cybersecuritydemexico.com.mx,banxico@cybersecuritydemexico.com.mx,soporte_uem@cybersecuritydemexico.com.mx,asistencia@cybersecuritydemexico.com.mx" # Cambia a tu dirección

    # Crear el mensaje de correo
    msg = MIMEMultipart()
    msg['From'] = smtp_username
    msg['To'] = email_to
    msg['Subject'] = "[BLACKBERRY] Ticket generado por DOMO ({})".format(data["ticket"])

    # Cuerpo del correo
    email_body = "Ticket generado exitosamente.\n"
    for key, val in data.items():
        email_body += f"{key} = {val}\n"

    msg.attach(MIMEText(email_body, 'plain'))

    # Conectar al servidor SMTP y enviar el correo
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Habilitar TLS
        server.login(smtp_username, smtp_password)  # Iniciar sesión en el servidor SMTP
        server.send_message(msg)  # Enviar el mensaje
        return "Correo electrónico enviado exitosamente."
    except Exception as e:
        return f"Error al enviar el correo: {e}"
    finally:
        server.quit()  # Cerrar la conexión con el servidor

def Run(call, config):
    """
    Friendly Name: Email Tagger

    Description:
    Este hook envía un correo electrónico una vez que la llamada ha finalizado. Se puede etiquetar la llamada y luego enviar un correo con los detalles.

    Hook Type: POST_CALL

    Logo URL: https://example.com/logo.png
    """

    logger.debug(f"Objeto call: {call}")
    if call.callScript:
        data = Analyze(call, config)
        if data:
            data["ticket"] = "BB-{}".format(str(call.id).zfill(4))
            data["time"] = call.callTime

            send_ticket_email(data)

            return True
    return False
