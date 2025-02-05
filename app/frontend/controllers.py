import json
import os
import platform
from openai import OpenAI
from datetime import datetime
from threading import Thread
from app.models.File import File
from app.models.Call import Call
from app.models.Message import Message
from app.models.Config import Config
from app.models.Notification import Notification
from app.util.database import LocalStorage
from app.outbound import InitOutboundCalls
from datetime import datetime
class Context:
    def __init__(self, fragment, method, payload=None):
        self.__fragment = fragment
        self.__ls = LocalStorage()
        self.method = method
        self.payload = payload
        if self.payload and 'file' in self.payload:
            self.payload['file'] = self.payload['file'].filename
    
    def prepare(self, **kwargs):
        configs = { c.name:c.value for c in self.__ls.GetAll(Config) }
        q = "SELECT CASE WHEN EXISTS (SELECT 1 FROM notifications WHERE \"nAck\" = false) THEN 'true' ELSE 'false' END AS \"hasNotifications\""
        response = self.__ls.GetAll(Notification, q, True)[0]
        response["power"] = (configs.get("power") or "false") == "true"

        if hasattr(self, f"_Context__{self.__fragment}"):
            response.update(getattr(self, f"_Context__{self.__fragment}")(**kwargs))
        
        return response
    
    def __dashboard(self, **kwargs):
        q = "SELECT * FROM calls WHERE DATE(\"callTime\") = DATE('now');"
        calls = self.__ls.GetAll(Call, q, True)
        inp = [c for c in calls if 'progress' in c['callStatus'].lower() ]

        for c in inp:
            c['callTime'] = c['callTime'].split(' ')[1] 

        response = {
            "title": "Dashboard",
            "graphs": [],
            "calls": inp,
            "inProgress": len([c for c in calls if 'progress' in c['callStatus'].lower() ]),
            "completed": len([c for c in calls if c['callStatus'] in ['COMPLETED', 'PARTIAL_COMPLETED'] ]),
            "noContact": len([c for c in calls if 'NO_CONTACT' == c['callStatus'] ]),
            "amd": len([c for c in calls if 'AMD' == c['callStatus'] ])
        }

        days = kwargs.get("days") or "15"
        q = "SELECT DATE(\"callTime\") AS callDate, COUNT(*) AS totalCalls FROM calls WHERE \"callStatus\" = '{}' AND DATE(\"callTime\") >= CURRENT_DATE - INTERVAL '{} days' GROUP BY callDate ORDER BY callDate DESC"
        for status in ['COMPLETED', 'NO_CONTACT', 'AMD']:
            response['graphs'].append({ "type": status, "records": self.__ls.GetAll(Call, q.format(status, days), True) })

        return response

    def __logs(self, **kwargs):
        call = self.__ls.GetByPK(Call, kwargs['id'], json=True)
        return { "logs": call['callLogs'] }

    def __audio(self, **kwargs):
        call = self.__ls.GetByPK(Call, kwargs['id'], json=True)
        if call["callPlayback"]:
            return { "audios": json.loads(call['callPlayback']) }
        
        return { "audios": [] }
    
    
    def __script(self, **kwargs):
        call = self.__ls.GetByPK(Call, kwargs['id'], json=True)
        if call["callScript"]:
            return { "script": json.loads(call['callScript']) }
        return { "script": [] }

    
    def __messages(self, **kwargs):
        messages = self.__ls.Search(Message(number=kwargs['id']), json=True, order='asc')
        return { "script": messages }

    def __health(self, **kwargs):
        return { "title": "System Health"}
    
    def __callfiles(self, **kwargs):
        Thread(target=InitOutboundCalls, args=(kwargs['id'], )).start()
        return { "message": "The call initialization process has been started in BACKGROUND!" }
    
    def __remfiles(self, **kwargs):
        file = self.__ls.Search(File(name=kwargs['id']), True)
        
        if file:
            self.__ls.Remove(file)
        
        return {
            "files": self.__ls.GetAll(File, cols=['name', 'ftype'], json=True)
        }

    def __chats(self, **kwargs):
        q = 'SELECT "senderName", number, MAX(time) AS time FROM messages GROUP BY "senderName", number;'
        messages = self.__ls.GetAll(Message, q, json=True)

        return { "title": "Chat Records", "logs": messages }

    def __calls(self, **kwargs):
        excluded = ['callScript', 'callLogs', 'callPlayback']
        logs = self.__ls.GetAll(Call, json=True)

        if "person" in kwargs:
            logs = [ log for log in logs if log["callerName"] == kwargs["person"]]
        
        if "filter" in kwargs:
            logs = [ log for log in logs if log["callStatus"] == kwargs["filter"]]

        for log in logs:
            if log['callDuration'] == None:
                continue

            minutes = log['callDuration'] // 60
            seconds = log['callDuration'] % 60
            log['callDuration'] = f"{minutes:02d}:{seconds:02d}"

            log["hasChat"] = log["callScript"] != None
            log["hasLogs"] = log["callLogs"] != None
            log["hasPlayback"] = log["callPlayback"] != None

            for col in excluded:
                if col in log:
                    del log[col]

        return {
            "title": "Call Logs",
            "logs": reversed(logs)
        }

    def __settings(self, **kwargs):
        configs = { c.name:c.getval() for c in self.__ls.GetAll(Config) }
        configs["datetime"] = datetime.now().strftime('%Y-%m-%dT%H:%M')
        configs["models"] = []

        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        for model in client.models.list().data:
            model_dict = {
                'id': model.id,
                'created_at': model.created if hasattr(model, 'created') else '',
                'owner': model.owned_by if hasattr(model, 'owned_by') else ''
            }
            configs["models"].append(model_dict)

        prompt = configs.get("prompt", "")
        if "prompt" in configs:
            del configs["prompt"]

        return {
            "title": "Robot Configurations",
            "prompt": prompt,
            "files": self.__ls.GetAll(File, cols=['name', 'ftype'], json=True),
            "configs": configs
        }

    def __notifications(self, **kwargs):
        return {
            "title": "Notifications",
            "notifications": self.__ls.GetAll(Notification, json=True)
        }
    
    def __power(self, **kwargs):
        power = [ c for c in self.__ls.GetAll(Config) if c.name == 'power' ][0]
        power.value = str(kwargs['id'] == '1').lower()
        self.__ls.Update(power)
        return { "status": True }
    
    def __configs(self, **kwargs):
        if self.payload:
            if "datetime" in self.payload:
                datetime_obj = datetime.strptime(self.payload["datetime"], '%Y-%m-%dT%H:%M')
                if platform.system() == 'Windows':
                    formatted_time = datetime_obj.strftime('%m-%d-%Y %H:%M:%S')
                    os.system(f'date {formatted_time.split()[0]}')
                    os.system(f'time {formatted_time.split()[1]}')
                else:
                    formatted_time = datetime_obj.strftime('%Y-%m-%d %H:%M:%S')
                    os.system(f'date -s "{formatted_time}"')
                del self.payload["datetime"]

            for key, value in self.payload.items():
                config = Config(name=key)
                config = self.__ls.Search(config, True, False)
                if config:
                    config.value = value
                    self.__ls.Update(config)
                else:
                    self.__ls.Insert(Config(name=key, value=value))
        return { "status": True }

