import os
import json
import requests
from dotenv import load_dotenv

from backend.app.services.weather_steps_service import get_weather_current_step

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

# Register your functions in a dictionary
TOOLS = {
    "get_weather": get_weather_current_step,
}

def handle_message(message: str, step: int):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # Define tool schema for GPT
    tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "get_weather_current_step",
            "description": "Get the weather information for a specific step in the process",
            "parameters": {
                "type": "object",
                "properties": {
                    "step": {
                        "type": "integer",
                        "description": "The step number to retrieve weather information for"
                    }
                },
                "required": ["step"]
            }
        }
    }
]
    extra_context = f"Current step: {step}, you can choose a function to call based on the users message. If no function is relevant, respond with nothing. "

    # Ask GPT which function to call
    payload = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": extra_context + message}],
        "tools": tools_schema
    }

    response = requests.post(url, headers=headers, data=json.dumps(payload))
    response_json = response.json()

    # Get GPT's chosen tool and arguments
    tool_call = response_json["choices"][0]["message"].get("tool_calls", None)
    if not tool_call:
        return "GPT did not choose a function."

    fn_name = tool_call[0]["function"]["name"]
    args = json.loads(tool_call[0]["function"]["arguments"])

    # Execute the chosen Python function
    if fn_name in TOOLS:
        result = TOOLS[fn_name](**args)
        return result
    else:
        return f"Function {fn_name} not found."