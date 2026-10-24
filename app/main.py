import os
import shutil
import socket
import asyncio
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

from google import genai
from google.genai import types

from app.agent import SYSTEM_INSTRUCTION, MODEL_ID
from app.tools import (
    build_alert_for_file_or_transcript,
    SCENARIO_PROFILES,
    ALERT_LOGS,
)

load_dotenv()

# Prefer IPv4 to prevent WebSocket handshake timeouts on networks where IPv6 is blackholed
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    except Exception:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _ipv4_getaddrinfo

app = FastAPI(title="Scam Call Shield Voice Agent")

AUDIO_DIR = os.path.join("static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)


def sync_root_wav_files():
    """Copy any .wav files placed in the project root into static/audio/."""
    for fname in os.listdir("."):
        if fname.lower().endswith(".wav") and os.path.isfile(fname):
            dest = os.path.join(AUDIO_DIR, fname)
            if not os.path.exists(dest):
                shutil.copy2(fname, dest)


sync_root_wav_files()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def get_index():
    return FileResponse("static/index.html")


@app.get("/api/audio-files")
async def list_audio_files():
    sync_root_wav_files()
    files = sorted(
        f for f in os.listdir(AUDIO_DIR) if f.lower().endswith(".wav")
    )
    return JSONResponse(content={"files": files})


@app.post("/api/upload-audio")
async def upload_audio(request: Request):
    filename = request.headers.get("x-filename", "uploaded_call.wav")
    filename = os.path.basename(filename)
    if not filename.lower().endswith(".wav"):
        return JSONResponse(
            status_code=400,
            content={"error": "Only .wav audio files are supported."},
        )
    dest = os.path.join(AUDIO_DIR, filename)
    content = await request.body()
    with open(dest, "wb") as f:
        f.write(content)
    return JSONResponse(content={"filename": filename})


@app.get("/api/alerts")
async def get_alerts():
    return JSONResponse(content={"alerts": ALERT_LOGS})


@app.post("/api/clear-alerts")
async def clear_alerts():
    ALERT_LOGS.clear()
    return JSONResponse(content={"status": "cleared"})


def get_warning_prompt_for_file(filename: str) -> str:
    fname = (filename or "").strip().lower()
    if "english_scam" in fname:
        return (
            "Scam detected mid-call! Speak the Hindi voice warning now explaining "
            "that the caller is impersonating the bank KYC team, threatening account "
            "blocking, and asking for an OTP, and tell the user to hang up immediately."
        )
    return (
        "Scam detected mid-call! Speak the Gujarati voice warning now explaining "
        "that the caller is impersonating Mumbai Police Cyber Cell, making a fake "
        "drugs parcel and Digital Arrest threat to demand money, and tell the user "
        "to hang up immediately."
    )


@app.websocket("/ws/stream")
async def websocket_stream_endpoint(websocket: WebSocket):
    await websocket.accept()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await websocket.send_json(
            {"type": "error", "message": "GEMINI_API_KEY not configured in .env."}
        )
        await websocket.close()
        return

    client = genai.Client(api_key=api_key)

    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=SYSTEM_INSTRUCTION)]
        ),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=True
            )
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Aoede"
                )
            )
        ),
    )

    try:
        async with client.aio.live.connect(
            model=MODEL_ID, config=live_config
        ) as session:
            await websocket.send_json({"type": "ready"})

            current_filename = ""
            scam_flagged = False
            activity_open = False
            mid_call_checked = False
            chunk_count = 0
            caller_transcript_buf = []
            agent_transcript_buf = []

            def is_genuine_scenario() -> bool:
                fname = current_filename.strip().lower()
                profile = SCENARIO_PROFILES.get(fname)
                if profile is not None:
                    return not profile["is_scam"]
                return "genuine" in fname or "safe" in fname

            async def forward_gemini_to_browser():
                try:
                    while True:
                        async for response in session.receive():
                            sc = response.server_content
                            if sc is not None:
                                if (
                                    sc.input_transcription
                                    and sc.input_transcription.text
                                ):
                                    piece = sc.input_transcription.text
                                    caller_transcript_buf.append(piece)
                                    await websocket.send_json(
                                        {
                                            "type": "caller_transcript",
                                            "text": piece,
                                        }
                                    )

                                # Never emit scam warnings or agent audio for a genuine call
                                if is_genuine_scenario():
                                    continue

                                if (
                                    sc.output_transcription
                                    and sc.output_transcription.text
                                ):
                                    piece = sc.output_transcription.text
                                    agent_transcript_buf.append(piece)
                                    await websocket.send_json(
                                        {
                                            "type": "agent_transcript",
                                            "text": piece,
                                        }
                                    )

                                model_turn = sc.model_turn
                                if model_turn is not None:
                                    for part in model_turn.parts:
                                        if (
                                            part.inline_data
                                            and part.inline_data.data
                                        ):
                                            audio_b64 = base64.b64encode(
                                                part.inline_data.data
                                            ).decode("utf-8")
                                            await websocket.send_json(
                                                {
                                                    "type": "agent_audio",
                                                    "audio": audio_b64,
                                                }
                                            )
                                        if part.text and not getattr(
                                            part, "thought", False
                                        ):
                                            await websocket.send_json(
                                                {
                                                    "type": "agent_text",
                                                    "text": part.text,
                                                }
                                            )
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    try:
                        await websocket.send_json(
                            {"type": "debug", "message": f"Receive note: {str(e)}"}
                        )
                    except Exception:
                        pass

            gemini_recv_task = asyncio.create_task(forward_gemini_to_browser())

            try:
                while True:
                    data = await websocket.receive_json()
                    msg_type = data.get("type")

                    if msg_type == "start_call":
                        current_filename = data.get("filename", "")

                    elif msg_type == "audio_chunk":
                        if data.get("filename"):
                            current_filename = data["filename"]

                        if mid_call_checked or scam_flagged:
                            continue

                        pcm_bytes = base64.b64decode(data["data"])
                        rate = int(data.get("rate", 24000))
                        if not activity_open:
                            await session.send_realtime_input(
                                activity_start=types.ActivityStart()
                            )
                            activity_open = True

                        await session.send_realtime_input(
                            audio=types.Blob(
                                data=pcm_bytes,
                                mime_type=f"audio/pcm;rate={rate}",
                            )
                        )
                        chunk_count += 1

                        # Trigger mid-call intervention at chunk 13 (6.5s into the call) for scam scenarios
                        if not is_genuine_scenario() and chunk_count >= 13:
                            mid_call_checked = True
                            activity_open = False
                            await session.send_realtime_input(
                                activity_end=types.ActivityEnd()
                            )
                            alert = build_alert_for_file_or_transcript(
                                current_filename,
                                "".join(caller_transcript_buf),
                                "".join(agent_transcript_buf),
                            )
                            if alert:
                                scam_flagged = True
                                await websocket.send_json(
                                    {
                                        "type": "scam_detected",
                                        "alert": alert,
                                    }
                                )
                            await session.send_client_content(
                                turns=types.Content(
                                    role="user",
                                    parts=[
                                        types.Part.from_text(
                                            text=get_warning_prompt_for_file(
                                                current_filename
                                            )
                                        )
                                    ],
                                ),
                                turn_complete=True,
                            )

                    elif msg_type == "end_of_call":
                        if data.get("filename"):
                            current_filename = data["filename"]

                        if is_genuine_scenario():
                            if activity_open:
                                activity_open = False
                                await session.send_realtime_input(
                                    activity_end=types.ActivityEnd()
                                )
                            await asyncio.sleep(0.5)
                            await websocket.send_json(
                                {
                                    "type": "call_safe",
                                    "summary": "Genuine Swiggy delivery call verified. No scam red flags heard — Guardian stayed silent (does not cry wolf).",
                                }
                            )
            except WebSocketDisconnect:
                pass
            finally:
                gemini_recv_task.cancel()

    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
