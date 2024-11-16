import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from twilio.rest import Client

client = Client("AC274ae17c4a1dc4f8d1097d5b7f03aef3", "d2ffb52730a5a6284cce5836ff86c7aa")

try:
    message = client.messages.create(
        body=input("Enter Message: ") or "This is a test message from python3 Twillio client",
        from_=input("Enter From Number: ") or "whatsapp:+5213341611086",
        to=input("Enter to Number: ") or "whatsapp:+5218181850026"
    )
    print("Message has been sent Successfully", message)
except Exception as e:
    print(e)