import os
import json
import httpx
from dotenv import load_dotenv

from app.services.weather_steps_service import get_weather_current_step
from app.services.city_state_steps_service import get_city_state_current_step

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

# Register your functions in a dictionary
TOOLS = {
    "get_weather_current_step": get_weather_current_step,
    "get_city_state_current_step": get_city_state_current_step,
}

async def handle_message(message: str, step: int):

    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    tools_schema = [
        {
            "type": "function",
            "function": {
                "name": "get_weather_current_step",
                "description": "Get weather for a specific step",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "step": {
                            "type": "integer"
                        }
                    },
                    "required": ["step"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_city_state_current_step",
                "description": "Get information about city/state level alerts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "step": {
                            "type": "integer"
                        }
                    },
                    "required": ["step"]
                }
            }
        }
    ]

    extra_context = f"Current step: {step}. Decide if the function(s) should be called."

    payload = {
        "model": "gpt-4.1-mini",
        "messages": [
            {"role": "user", "content": extra_context + message}
        ],
        "tools": tools_schema,
        "tool_choice": "auto"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)

    response_json = response.json()

    print("Tool decision:", response_json)

    tool_calls = response_json["choices"][0]["message"].get("tool_calls") or []

    if not tool_calls:
        return ""

    def _to_serializable(value):
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
            return value
        return str(value)

    results = []
    for call in tool_calls:
        fn_name = call["function"]["name"]
        args = json.loads(call["function"]["arguments"])

        if fn_name in TOOLS:
            result = await TOOLS[fn_name](**args)
            serialized = _to_serializable(result)
            results.append({"function": fn_name, "args": args, "result": serialized})
            print(f"Function {fn_name} called with args {args}, result: {serialized}")

    if not results:
        return ""

    return json.dumps(results, indent=2)
