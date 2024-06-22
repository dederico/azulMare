import json
from app.models.Call import Call
from app.models.Notification import Notification
from app.util.database import LocalStorage

class Context:
    def __init__(self, fragment):
        self.__fragment = fragment
        self.__ls = LocalStorage()
    
    def prepare(self, **kwargs):
        if hasattr(self, f"_Context__{self.__fragment}"):
            return getattr(self, f"_Context__{self.__fragment}")(**kwargs)
        
        return {}
    
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
            "error": len([c for c in calls if 'error' in c['callStatus'].lower() ])
        }

        days = kwargs.get("days") or "15"
        q = "SELECT DATE(callTime) AS callDate, COUNT(*) AS totalCalls FROM calls WHERE callStatus = '{}' AND DATE(callTime) >= DATE('now', '-{} days') GROUP BY callDate ORDER BY callDate DESC;"
        for status in ['COMPLETED', 'HANGED_UP', 'COMPLETED_WITH_ERROR']:
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
    
    def __notifications(self, **kwargs):
        return {
            "title": "Notifications",
            "notifications": self.__ls.GetAll(Notification, json=True)
        }
