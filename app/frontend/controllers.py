import json
import os
from threading import Thread
from app.models.Call import Call
from app.models.Config import Config
from app.models.Notification import Notification
from app.util.database import LocalStorage
from app.outbound import InitOutboundCalls

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
        q = "SELECT CASE WHEN MAX(CASE WHEN nAck = 0 THEN 1 ELSE 0 END) = 1 THEN 'true' ELSE 'false' END AS hasNotifications FROM notifications;"
        response = self.__ls.GetAll(Notification, q, True)[0]
        response["power"] = (configs.get("Power") or "false") == "true"

        if hasattr(self, f"_Context__{self.__fragment}"):
            response.update(getattr(self, f"_Context__{self.__fragment}")(**kwargs))
        
        return response
    
    def __dashboard(self, **kwargs):
        q = "SELECT * FROM calls WHERE DATE(callTime) = DATE('now');"
        calls = self.__ls.GetAll(Call, q, True)
        inp = [c for c in calls if 'progress' in c['callStatus'].lower() ]

        for c in inp:
            c['callTime'] = c['callTime'].split(' ')[1] 

        response = {
            "title": "Dashboard",
            "graphs": [],
            "calls": inp,
            "inProgress": len([c for c in calls if 'progress' in c['callStatus'].lower() ]),
            "completed": len([c for c in calls if 'COMPLETED' == c['callStatus'] ]),
            "hanged": len([c for c in calls if 'hanged' in c['callStatus'].lower() ]),
            "error": len([c for c in calls if 'partial' in c['callStatus'].lower() ])
        }

        days = kwargs.get("days") or "15"
        q = "SELECT DATE(callTime) AS callDate, COUNT(*) AS totalCalls FROM calls WHERE callStatus = '{}' AND DATE(callTime) >= DATE('now', '-{} days') GROUP BY callDate ORDER BY callDate DESC;"
        for status in ['COMPLETED', 'HANGED_UP', 'PARTIAL_COMPLETED']:
            response['graphs'].append({ "type": status, "records": self.__ls.GetAll(Call, q.format(status, days), True) })

        return response

    def __logs(self, **kwargs):
        call = self.__ls.GetByPK(Call, kwargs['id'], json=True)
        return { "logs": call['callLogs'] }

    def __script(self, **kwargs):
        call = self.__ls.GetByPK(Call, kwargs['id'], json=True)
        return {
            "script": json.loads(call['callScript'])
        }

    def __health(self, **kwargs):
        return { "title": "System Health"}
    
    def __callfiles(self, **kwargs):
        Thread(target=InitOutboundCalls, args=(kwargs['id'], )).start()
        return { "message": "The call initialization process has been started in BACKGROUND!" }
    
    def __remfiles(self, **kwargs):
        os.remove("uploads/{}".format(kwargs['id']))
        return {
            "files": os.listdir("uploads")
        }

    def __calls(self, **kwargs):
        excluded = ['callScript', 'callLogs']
        logs = self.__ls.GetAll(Call, json=True)
        for log in logs:
            if log['callDuration'] == None:
                continue

            minutes = log['callDuration'] // 60
            seconds = log['callDuration'] % 60
            log['callDuration'] = f"{minutes:02d}:{seconds:02d}"
            for col in excluded:
                del log[col]

        return {
            "title": "Call Logs",
            "logs": reversed(logs)
        }

    def __settings(self, **kwargs):
        return {
            "title": "Robot Configurations",
            "files": [f for f in os.listdir("uploads") if f.endswith('.xls') or f.endswith(".xlsx")],
            "configs": { c.name:c.value for c in self.__ls.GetAll(Config) }
        }

    def __notifications(self, **kwargs):
        return {
            "title": "Notifications",
            "notifications": self.__ls.GetAll(Notification, json=True)
        }
    
    def __power(self, **kwargs):
        power = [ c for c in self.__ls.GetAll(Config) if c.name == 'Power' ][0]
        power.value = str(kwargs['id'] == '1').lower()
        self.__ls.Update(power)
        return { "status": True }
    
    def __configs(self, **kwargs):
        if self.payload:
            for key, value in self.payload.items():
                config = Config(name=key)
                config = self.__ls.Search(config, True, False)
                if config:
                    config.value = value
                    self.__ls.Update(config)
                else:
                    self.__ls.Insert(Config(name=key, value=value))
        return { "status": True }

