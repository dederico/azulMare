import re
import pkgutil
import importlib
import inspect
import app.services.functions.hooks

class Hooks:
    def __init__(self):
        pass

    def __get_entrypoint(self, module_name):
        module = importlib.import_module(module_name)
        return {name: func for name, func in module.__dict__.items() if inspect.isfunction(func)}["Run"]

    def __list_modules(self, package):
        package_name = package.__name__
        modules = []
        for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
            full_modname = f"{package_name}.{modname}"
            modules.append(full_modname)
        return modules

    def Get(self, getEntrypoint=False):
        hooks = []
        for module in self.__list_modules(app.services.functions.hooks):
            hooks.append(self.__parse_docstring(self.__get_entrypoint(module), getEntrypoint))
        return hooks

    def __parse_docstring(self, func, getEntrypoint):
        docstring = func.__doc__
        if not docstring:
            return None

        detail = { "function": func } if getEntrypoint else {}

        friendly_name_match = re.search(r'Friendly Name: (.+)', docstring)
        detail["name"] = friendly_name_match.group(1) if friendly_name_match else None

        description_match = re.search(r'Description:\n(.+?)(\n\s*\n|$)', docstring, re.DOTALL)
        detail["description"] = description_match.group(1).strip() if description_match else None

        logo_url_match = re.search(r'Logo URL: (.+)', docstring)
        detail["logo"] = logo_url_match.group(1) if logo_url_match else None

        hook_type = re.search(r'Hook Type: (.+)', docstring)
        detail["type"] = hook_type.group(1) if hook_type else None

        return detail