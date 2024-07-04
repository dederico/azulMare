from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from twilio.base.exceptions import TwilioRestException
import os
from dotenv import load_dotenv
import openpyxl
from io import BytesIO
from datetime import datetime
from app.util.logger import logger
from app.models.Config import Config
from app.models.File import File
from app.models.Call import Call
from app.util.database import LocalStorage

load_dotenv(".env")

NGROK_URL = os.environ.get("HOSTNAME")
account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

def make_twilio_call(to_phone_number, from_phone_number):
    client = Client(account_sid, auth_token)
    call = client.calls.create(
        to=to_phone_number,
        from_=from_phone_number,
        url=f"{NGROK_URL}/",
        machine_detection="Enable",
        async_amd="Enable",
        async_amd_status_callback=f"{NGROK_URL}/amd_detect",
    )
    return call.sid

def InitOutboundCalls(file):
    ls = LocalStorage()
    configs = { c.name:c.value for c in ls.GetAll(Config) }

    if not "from_phone_number" in configs:
        logger.warning("Skipping outbound calls as FROM_PHONE_NO not configured yet")
        return False

    file = ls.Search(File(name=file), True)
    file = BytesIO(file.data)
    workbook = openpyxl.load_workbook(filename=file)
    worksheet = workbook.active

    header_values = [cell.value for cell in worksheet[1]]
    phone_index = header_values.index('phone_number')
    name_index = header_values.index('name')

    for row_index in range(2, worksheet.max_row + 1):
        record = [cell.value for cell in worksheet[row_index]]
        name = record[name_index] if name_index != -1 else 'Unknown'

        try:
            if phone_index != -1 and phone_index < len(record):
                phone_number = record[phone_index]
                name = record[name_index] if name_index != -1 else 'Unknown'

                call_sid = make_twilio_call(phone_number, configs["from_phone_number"])
                if call_sid:
                    call = Call(
                        callerName = name,
                        callSource = 'Twilio',
                        callNumber = phone_number,
                        callStatus = 'NO_CONTACT',
                        callType = 'IP',
                        callDirection = 'OUT_GOING',
                        callUid = call_sid,
                        callTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    ls.Insert(call)
                    logger.info("Outbound call to {} has been made successfully".format(phone_number))
                else:
                    logger.error("Outbound call to {} is FAILED".format(phone_number))
        except Exception as e:
            logger.critical(e)