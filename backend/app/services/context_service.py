from openai import OpenAI
import json

load_dotenv()
client = OpenAI()

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"}
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Get stock price for ticker",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"}
                },
                "required": ["ticker"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "What is the price of AAPL?"}],
    tools=tools
)

tool_call = response.choices[0].message.tool_calls
print(tool_call)