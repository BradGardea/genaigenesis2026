import os
import json
import httpx
from dotenv import load_dotenv

from app.services.person_relationships_service import get_first_person_help_needed
from app.services.weather_steps_service import get_weather_current_step
from app.services.city_state_steps_service import get_city_state_current_step

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

async def get_community_current_step(step: int):
    help_needed = await get_first_person_help_needed(step)
    if not help_needed.help_needed:
        return {
            "step_index": step,
            "summary": "None of your direct connections are currently flagged as needing help.",
            "help_needed": [],
        }

    return {
        "step_index": step,
        "summary": "These direct connections currently need help.",
        "help_needed": [
            {
                "name": node.person.name,
                "relationship": node.relationship,
                "scenario": node.person.scenario,
                "seats_available": node.person.seats_available,
                "current_position": node.person.current_position,
                "event": node.emergency_event.model_dump() if node.emergency_event else None,
            }
            for node in help_needed.help_needed
        ],
    }

# Register your functions in a dictionary
TOOLS = {
    "get_weather_current_step": get_weather_current_step,
    "get_city_state_current_step": get_city_state_current_step,
    "get_community_current_step": get_community_current_step,
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
        },
        {
            "type": "function",
            "function": {
                "name": "get_community_current_step",
                "description": "Get which of the user's direct connections currently need help, especially evacuation ride requests.",
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
    print("Sending message to OpenAI with context:", extra_context)

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
