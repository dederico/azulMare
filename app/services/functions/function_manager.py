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

        # Pattern to extract parameters with optional modifiers
        # Supports: param_name (type): description
        # or: param_name (type, optional): description  
        # or: param_name (array[type]): description
        param_pattern = re.compile(r"(\w+) \(([^)]+)\): (.+)")
        
        for line in description_lines:
            match = param_pattern.match(line.strip())
            if match:
                param_name, param_type_full, param_desc = match.groups()
                
                # Parse the type and check if it's optional
                is_optional = False
                if ", optional" in param_type_full:
                    is_optional = True
                    param_type_full = param_type_full.replace(", optional", "").strip()
                
                # Check if it's an array with specified item type
                array_match = re.match(r"array\[(\w+)\]", param_type_full)
                if array_match:
                    item_type = array_match.group(1)
                    parameters["properties"][param_name] = {
                        "type": "array",
                        "description": param_desc,
                        "items": {
                            "type": item_type
                        }
                    }
                elif param_type_full == "array":
                    # Default array type (string items)
                    parameters["properties"][param_name] = {
                        "type": "array",
                        "description": param_desc,
                        "items": {
                            "type": "string"
                        }
                    }
                else:
                    # Handle type mapping for JSON Schema compatibility
                    json_type = self._map_to_json_type(param_type_full)
                    parameters["properties"][param_name] = {
                        "type": json_type,
                        "description": param_desc,
                    }
                
                # Add to required list if not optional and has no default
                if param_name in signature.parameters:
                    param = signature.parameters[param_name]
                    if (not is_optional and 
                        param.default is inspect.Parameter.empty and 
                        param_name != "yoga_number"):
                        parameters["required"].append(param_name)

        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": description,
                "parameters": parameters,
            },
        }
    
    def _map_to_json_type(self, param_type: str) -> str:
        """Map Python/custom types to valid JSON Schema types."""
        type_mapping = {
            "bool": "boolean",
            "boolean": "boolean", 
            "int": "number",
            "integer": "number",
            "float": "number",
            "number": "number",
            "str": "string",
            "string": "string"
        }
        return type_mapping.get(param_type.lower(), "string")  # Default to string if unknown