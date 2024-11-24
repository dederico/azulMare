import json
from io import BytesIO
from dotenv import load_dotenv
from app.util.helpers import getAPIKey
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi import FastAPI, APIRouter, Request
from app.models.Call import Call, CallResponse, ScriptResponse
from app.models.Notification import Notification, NotificationResponse
from app.models.Message import Message, MessageResponse, MessageResponseSenders
from app.models.Config import Config
from app.util.database import LocalStorage

from app.util.helpers import combine_audio_segments
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader, APIKey
from starlette.status import HTTP_403_FORBIDDEN
from typing import List, Optional
from pydantic import BaseModel

load_dotenv()
router = APIRouter()

class GeneralResponse(BaseModel):
    status: bool
    message: str

app = FastAPI(
    title=f"Developer API's",
    description="The API provides a set of comprehensive endpoints designed for seamless integration with third-party CRM systems and platforms. These endpoints facilitate access to server data, enabling external applications to retrieve, update, and manage information efficiently. The integration capabilities range from basic operations to more advanced, medium-level functionalities, offering flexibility for various use cases. This ensures that external systems can easily interact with and leverage the server's data, supporting a wide array of integration scenarios in a secure and scalable manner.",
    version="1.0.0",
    terms_of_service="http://example.com/terms/",
    contact={
        "name": "Zain Ul Abidin",
        "url": "https://github.com/zedstron/",
        "email": "zain26134@gmail.com",
    }
)

api_key = APIKeyHeader(name="key", auto_error=False)

async def validate_auth(key: str = Depends(api_key)):
    if key != getAPIKey():
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, 
            detail="Could not validate API credentials"
        )

@router.get("/calls", dependencies=[Depends(validate_auth)], response_model=List[CallResponse], tags=['Calls'])
async def calls(request: Request, callUid: Optional[str] = None, callerName: Optional[str] = None, callNumber: Optional[str] = None, callStatus: Optional[str] = None, callDirection: Optional[str] = None, callTime: Optional[str] = None):
    ls = LocalStorage()
    cols = ['id', 'callUid', 'callerName', 'callNumber', 'callStatus', 'callDirection', 'callDuration', 'callTime']
    if len(request.query_params.keys()) == 0:
        calls = ls.GetAll(Call, json=True, cols=cols)
    else:
        calls = ls.Search(Call(**request.query_params), json=True, cols=cols)
    
    return JSONResponse(calls)

@router.delete("/calls", dependencies=[Depends(validate_auth)], response_model=GeneralResponse, tags=['Calls'])
async def calls(request: Request):
    ls = LocalStorage()
    ls.Remove(Call(), allRecords=True)
    return JSONResponse({ "status": True, "message": "Cleared all call records successfully" })

@router.delete("/calls/{id}", dependencies=[Depends(validate_auth)], response_model=GeneralResponse, tags=['Calls'])
async def delete_call(request: Request, id: int):
    ls = LocalStorage()
    ls.Remove(Call(id=id))
    return JSONResponse({ "status": True, "message": "Successfully removed" })

@router.get("/calls/{id}", dependencies=[Depends(validate_auth)], response_model=CallResponse, tags=['Calls'])
async def call_by_pk(request: Request, id: int):
    ls = LocalStorage()
    call = ls.GetByPK(Call, id, json=True)

    for col in ['callScript', 'callPlayback', 'callLogs']:
        del call[col]

    return JSONResponse(call)

@router.get("/calls/{id}/script", dependencies=[Depends(validate_auth)], response_model=List[ScriptResponse], tags=['Calls'])
async def call_script(request: Request, id: int):
    ls = LocalStorage()
    response = ls.GetByPK(Call, id, json=True)
    if response:
        response = json.loads(response['callScript']) if response['callScript'] != None else False
        return JSONResponse(response or { "message": "No script found for the given call" })

    return JSONResponse({ "message": "No call record found for the given call id" })

@router.get("/calls/{id}/playback", dependencies=[Depends(validate_auth)], response_class=StreamingResponse, tags=['Calls'])
async def call_playback(request: Request, id: int):
    ls = LocalStorage()
    response = ls.GetByPK(Call, id, json=True)
    if response:
        response = json.loads(response['callPlayback']) if response['callPlayback'] != None else False
        if response:
            wav_data = combine_audio_segments(response)
            wav_file = BytesIO(wav_data)
            return StreamingResponse(wav_file, media_type="audio/wav", headers={"Content-Disposition": "attachment; filename=playback.wav"})
        return JSONResponse({ "message": "No playback available for the given call" })
    
    return JSONResponse({ "message": "No call record found for given call id" })

@router.get("/messages", dependencies=[Depends(validate_auth)], response_model=MessageResponseSenders, tags=['Messages'])
async def messages(request: Request):
    ls = LocalStorage()
    q = 'SELECT "senderName", number, MAX(time) AS time FROM messages WHERE direction = \'INBOUND\' GROUP BY "senderName", number;'

    return JSONResponse(ls.GetAll(Message, q, json=True))

@router.get("/messages/{uid}", dependencies=[Depends(validate_auth)], response_model=List[MessageResponse], tags=['Messages'])
async def messages_by_uid(request: Request, uid: int):
    ls = LocalStorage()
    return JSONResponse(ls.Search(Message(uid=uid), json=True, order='asc'))

@router.delete("/messages", dependencies=[Depends(validate_auth)], response_model=GeneralResponse, tags=['Messages'])
async def remove_all_messages(request: Request):
    ls = LocalStorage()
    ls.Remove(Message(), allRecords=True)
    return JSONResponse({ "status": True, "message": "Cleared all messages in the system" })

@router.delete("/messages/{uid}", dependencies=[Depends(validate_auth)], response_model=GeneralResponse, tags=['Messages'])
async def remove_messages(request: Request, uid: int):
    ls = LocalStorage()
    ls.Remove(Message(uid=uid))
    return JSONResponse({ "status": True, "message": "Cleared the chat conversation successfully!" })

@router.get("/notifications", dependencies=[Depends(validate_auth)], response_model=List[NotificationResponse], tags=['Notifications'])
async def notifications(request: Request):
    ls = LocalStorage()
    if len(request.query_params.keys()) == 0:
        notifs = ls.GetAll(Notification, json=True)
    else:
        notifs = ls.Search(Notification(**request.query_params), json=True)
    
    return JSONResponse(notifs)

@router.delete("/notifications/{id}", dependencies=[Depends(validate_auth)], response_model=GeneralResponse, tags=['Notifications'])
async def delete_notification(request: Request, id: int):
    ls = LocalStorage()
    ls.Remove(Notification(id=id))
    return JSONResponse({ "status": True, "message": "Successfully removed" })

@router.put("/notifications/{id}", dependencies=[Depends(validate_auth)], response_model=GeneralResponse, tags=['Notifications'])
async def update_notification(request: Request, id: int):
    body = await request.json()
    ls = LocalStorage()
    ls.Update(Notification(id=id, nAck=body.get("markRead", "true").lower() == "true"))
    return JSONResponse({ "status": True, "message": "Notification has been updated" })

@router.delete("/notifications", dependencies=[Depends(validate_auth)], response_model=GeneralResponse, tags=['Notifications'])
async def remove_all_notifications(request: Request):
    ls = LocalStorage()
    ls.Remove(Notification(), allRecords=True)
    return JSONResponse({ "status": True, "message": "Cleared all notifications from the system successfully!" })

app.include_router(router)