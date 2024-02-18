import re
from typing import Callable
import inspect
from openai.types.chat import ChatCompletionToolParam


class FunctionManager:
    def __init__(self, registered_functions: list[Callable]) -> None:
        self.registered_functions = registered_functions

    def get_function_definition(
        self, service: str = "openai"
    ) -> list[ChatCompletionToolParam]:
        if service == "openai":
            return self._get_function_definition_openai()
        else:
            raise NotImplementedError

    def _get_function_definition_openai(self):
        final_functions = []
        for func in self.registered_functions:
            func_schema = self._get_schema_openai(func)
            final_functions.append(func_schema)

        return final_functions

    def _get_schema_openai(self, func: Callable):
        signature = inspect.signature(func)
        description_lines = func.__doc__.strip().split("\n")  # type: ignore
        description = description_lines[0]

        parameters = {"type": "object", "properties": {}, "required": []}

        # Extracting parameter descriptions
        param_pattern = re.compile(r"(\w+) \((\w+)\): (.+)")
        for line in description_lines:
            match = param_pattern.match(line.strip())
            if match:
                param_name, param_type, param_desc = match.groups()
                parameters["properties"][param_name] = {
                    "type": param_type,
                    "description": param_desc,
                }
                if param_name in signature.parameters:
                    param = signature.parameters[param_name]
                    if param.default is inspect.Parameter.empty:
                        parameters["required"].append(param_name)

        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": description,
                "parameters": parameters,
            },
        }