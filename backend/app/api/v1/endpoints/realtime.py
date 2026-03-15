import os
import json
import asyncio
import websockets
from app.services.context_service import handle_message
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

router = APIRouter(prefix="/realtime", tags=["realtime"])

load_dotenv(".env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview"
print("Loaded OpenAI API Key:", OPENAI_API_KEY)

# ── Replace this with your real data-fetching logic ─────────────────────────
async def get_context_for_user(user_id: str, transcript: str, step_index: int) -> dict:
    """
    Fetch whatever backend data is relevant to this user + what they just said.
    Return a dict — it will be serialized and injected as context to GPT.
    """
    # TODO: replace with real DB / service calls, e.g.:
    #   user = await db.get_user(user_id)
    #   orders = await db.get_recent_orders(user_id)
    return {
        "user_id": user_id,
        "name": "Jane Doe",
        "account_status": "premium",
        "recent_orders": ["Order #1021 - pending"],
        "current_step_index": step_index,
    }
# ────────────────────────────────────────────────────────────────────────────

@router.get("/")
async def root():
    return {"status": "ok", "message": "GPT-4o Realtime proxy running"}


@router.websocket("/ws")
async def realtime_proxy(client_ws: WebSocket):
    await client_ws.accept()

    # The frontend sends a JSON handshake first: {"user_id": "abc123"}
    user_id = "anonymous"
    step_index = 0
    try:
        handshake_raw = await asyncio.wait_for(client_ws.receive_text(), timeout=5.0)
        handshake = json.loads(handshake_raw)
        user_id = handshake.get("user_id", "anonymous")
        step_index = int(handshake.get("step_index", 0))
        print(f"User connected: {user_id}")
    except Exception:
        print("No handshake received, using anonymous user")

    openai_headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1",
    }

    try:
        async with websockets.connect(
            OPENAI_REALTIME_URL,
            additional_headers=openai_headers,
        ) as openai_ws:
            print("Connected to OpenAI Realtime API")

            suppress_responses = True
            waiting_for_new_response = False
            expected_response_id = None

            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": (
                        "You are a helpful voice assistant for our app, where you assist users by providing helpful information and answering questions during a weather event, and potentially emergency scenario."
                        "Prioritize providing short answers with the most critical information"
                        "These responses are meant for users who may be in stressful situations, so clarity and brevity are important. You do not need to emphasize numberical metrics unless they are common knowledge."
                        "When you receive a [CONTEXT] block before the user's message, "
                        "use that data to personalize and inform your response. "
                        "Never read out the raw context to the user — just use it naturally."
                    ),
                    "voice": "alloy",
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": None,
                },
            }
            await openai_ws.send(json.dumps(session_config))

            async def client_to_openai():
                try:
                    while True:
                        message = await client_ws.receive_text()
                        try:
                            maybe_json = json.loads(message)
                            if isinstance(maybe_json, dict) and maybe_json.get("type") == "meta.step":
                                step_index = int(maybe_json.get("step_index", step_index))
                                print(f"Updated step_index to {step_index} for user {user_id}")
                                continue
                        except Exception:
                            pass
                        await openai_ws.send(message)
                except WebSocketDisconnect:
                    print(f"Client {user_id} disconnected")
                except Exception as e:
                    print(f"client_to_openai error: {e}")

            async def openai_to_client():
                nonlocal suppress_responses, waiting_for_new_response
                try:
                    async for raw_message in openai_ws:
                        msg = json.loads(raw_message)

                        if msg.get("type") == "conversation.item.input_audio_transcription.completed":
                            transcript = msg.get("transcript", "")
                            print(f"User said: {transcript}")

                            await client_ws.send_text(raw_message)

                            # 🛑 Cancel any response OpenAI started automatically
                            await openai_ws.send(json.dumps({
                                "type": "response.cancel"
                            }))

                            # Stop forwarding any in-flight response content until context is injected
                            suppress_responses = True
                            expected_response_id = None

                            context = await get_context_for_user(user_id, transcript, step_index)
                            context_str = json.dumps(context, indent=2)
                            extra = await handle_message(transcript, step=step_index)

                            inject_event = {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "input_text",
                                            "text": (
                                                "[CONTEXT — do not read aloud]\n"
                                                f"{context_str}\n"
                                                f"{extra}\n\n"
                                                f"User said: {transcript}"
                                            ),
                                        }
                                    ],
                                },
                            }

                            await openai_ws.send(json.dumps(inject_event))
                            print(f"Injected context for user {user_id}")

                            await openai_ws.send(json.dumps({"type": "response.create"}))
                            waiting_for_new_response = True

                        else:
                            # Skip any premature response frames until the contextual response is started
                            msg_type = msg.get("type", "")
                            if msg_type.startswith("response."):
                                # Capture the response id when created
                                if msg_type == "response.created":
                                    expected_response_id = msg.get("response_id")
                                    if waiting_for_new_response:
                                        suppress_responses = False
                                        waiting_for_new_response = False

                                if suppress_responses:
                                    continue

                                # If the response id does not match the expected contextual response, drop it
                                if expected_response_id and msg.get("response_id") not in (expected_response_id, None):
                                    continue

                            await client_ws.send_text(raw_message)

                except Exception as e:
                    print(f"openai_to_client error: {e}")

            await asyncio.gather(client_to_openai(), openai_to_client())

    except WebSocketDisconnect:
        print("Client disconnected before OpenAI connection")
    except Exception as e:
        print(f"Proxy error: {e}")
        try:
            await client_ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
    finally:
        print(f"Connection closed for user {user_id}")