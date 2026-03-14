import os
import json
import httpx
import requests
from dotenv import load_dotenv

from app.services.weather_steps_service import get_weather_current_step

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

# Register your functions in a dictionary
TOOLS = {
    "get_weather_current_step": get_weather_current_step,
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
        }
    ]

    extra_context = f"Current step: {step}. Decide if the function should be called."

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

    tool_call = response_json["choices"][0]["message"].get("tool_calls")

    if not tool_call:
        return ""

    fn_name = tool_call[0]["function"]["name"]
    args = json.loads(tool_call[0]["function"]["arguments"])

    if fn_name in TOOLS:
        result = await TOOLS[fn_name](**args)
        print(f"Function {fn_name} called with args {args}, result: {result}")
        return result

    return ""