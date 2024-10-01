# import smtplib
# from email.mime.text import MIMEText
# from email.mime.multipart import MIMEMultipart

# async def send_ticket_email(email_to: str):
#     """Envía un correo electrónico con un mensaje fijo de ticket generado.
    
#     Args:
#         email_to (string): Dirección de correo electrónico del destinatario.
        
#     Returns:
#         string: Mensaje de confirmación sobre el envío del correo.
#     """
#     # Configuración del servidor SMTP
#     smtp_server = "smtp.gmail.com"
#     smtp_port = 587
#     smtp_username = "dederico@gmail.com"  # Cambia a tu dirección de correo
#     smtp_password = "beas ajht qlgb eshd"  # Cambia a tu contraseña de correo
#     email_to = "dederico@gmail.com,soporte@cybersecuritydemexico.com.mx,banxico@cybersecuritydemexico.com.mx,soporte_uem@cybersecuritydemexico.com.mx,asistencia@cybersecuritydemexico.com.mx" # Cambia a tu dirección

#     # Crear el mensaje de correo
#     msg = MIMEMultipart()
#     msg['From'] = smtp_username
#     msg['To'] = email_to
#     msg['Subject'] = "[BLACKBERRY] Ticket generado por DOMO"

#     # Cuerpo del correo
#     email_body = "Ticket generado exitosamente."
#     msg.attach(MIMEText(email_body, 'plain'))

#     # Conectar al servidor SMTP y enviar el correo
#     try:
#         server = smtplib.SMTP(smtp_server, smtp_port)
#         server.starttls()  # Habilitar TLS
#         server.login(smtp_username, smtp_password)  # Iniciar sesión en el servidor SMTP
#         server.send_message(msg)  # Enviar el mensaje
#         return "Correo electrónico enviado exitosamente."
#     except Exception as e:
#         return f"Error al enviar el correo: {e}"
#     finally:
#         server.quit()  # Cerrar la conexión con el servidor
