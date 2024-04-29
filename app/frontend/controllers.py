from app.models.Call import Call
from app.util.database import LocalStorage

class Context:
    def __init__(self, fragment):
        self.__fragment = fragment
        self.__ls = LocalStorage()
    
    def prepare(self):
        if hasattr(self, f"_Context__{self.__fragment}"):
            return getattr(self, f"_Context__{self.__fragment}")()
        
        return {}
    
    def __dashboard(self, **kwargs):
        return {
            "title": "Dashboard"
        }

    def __calls(self, **kwargs):
        excluded = ['callScript', 'callLogs']
        logs = self.__ls.GetAll(Call, json=True)
        for log in logs:
            minutes = log['callDuration'] // 60
            seconds = log['callDuration'] % 60
            log['callDuration'] = f"{minutes:02d}:{seconds:02d}"
            for col in excluded:
                del log[col]

        return {
            "title": "Call Logs",
            "logs": logs
        }
