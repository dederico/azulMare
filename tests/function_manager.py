import inspect
import json
import re


async def get_credit_card_options():
    """Obtener informacion de las tarjetas de credito en caso de ser solicitada.

    Returns:
        string: Informacion de las tarjetas de credito.
    """
    return "test"


def generate_function_dict(func):
    signature = inspect.signature(func)
    description_lines = func.__doc__.strip().split("\n")
    description = description_lines[0]  # First line for the main description

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


# Example usage with your hangup function
print(json.dumps(generate_function_dict(get_credit_card_options), indent=2))