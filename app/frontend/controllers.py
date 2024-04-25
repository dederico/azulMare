class Context:
    def __init__(self, fragment):
        self.__fragment = fragment
    
    def prepare(self):
        if hasattr(self, f"_{self.__fragment}"):
            return getattr(self, f"_{self.__fragment}")()
        
        return {}
