class DirtyTrackingMeta(type):
    def __new__(cls, name, bases, dct):
        # Initialize a set to store dirty attribute names
        def __init__(self, **kwargs):
            # Initialize the set to store dirty attribute names
            self._dirty_attributes = set()
            for k, v in kwargs.items():
                super(self.__class__, self).__setattr__(k, v)

        dct['__init__'] = __init__

        # Override __setattr__ for the class being created
        def __setattr__(self, name, value):
            if not hasattr(self, '_dirty_attributes'):
                super(self.__class__, self).__setattr__('_dirty_attributes', set())
            if getattr(self, name, None) != value:
                self._dirty_attributes.add(name)
            super(self.__class__, self).__setattr__(name, value)
        
        dct['__setattr__'] = __setattr__

        # Add isDirty property
        @property
        def isDirty(self):
            return len(self._dirty_attributes) > 0
        
        dct['isDirty'] = isDirty
        
        # Create the class using the updated dictionary
        return super().__new__(cls, name, bases, dct)