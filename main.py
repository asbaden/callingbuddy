import os
import json
import base64
import logging
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from twilio.rest import Client
from dotenv import load_dotenv
import requests
from pydantic import BaseModel, Field
import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import schema initialization
try:
    from database.schema_init import init_schema
    # Attempt to initialize schema
    schema_initialized = init_schema()
    logger.info(f"Schema initialization: {'Success' if schema_initialized else 'Failed'}")
except Exception as schema_error:
    logger.error(f"Failed to initialize schema: {schema_error}")
    schema_initialized = False

# Import Supabase functions - with error handling built in
try:
    from database.supabase_client import (
        create_user, 
        get_user_by_phone,
        create_call,
        update_call,
        get_call_by_sid,
        create_transcription,
        get_transcription_by_call_id,
        supabase_available
    )
    logger.info(f"Supabase client imported successfully. Available: {supabase_available}")
except Exception as e:
    logger.error(f"Failed to import Supabase client: {e}")
    supabase_available = False
    # Define dummy functions if import fails
    async def create_user(phone_number, **kwargs):
        return {"id": "dummy-user-id", "phone_number": phone_number}
    
    async def get_user_by_phone(phone_number):
        return {"id": "dummy-user-id", "phone_number": phone_number}
    
    async def create_call(user_id, call_sid=None, **kwargs):
        return {"id": "dummy-call-id", "user_id": user_id, "call_sid": call_sid}
    
    async def update_call(call_id, **kwargs):
        return {"id": call_id}
    
    async def get_call_by_sid(call_sid):
        return {"id": "dummy-call-id", "call_sid": call_sid}
    
    async def create_transcription(call_id, content):
        logger.info(f"Transcription would have been stored: {content[:100]}...")
        return {"id": "dummy-transcription-id", "call_id": call_id}
    
    async def get_transcription_by_call_id(call_id):
        return {"id": "dummy-transcription-id", "call_id": call_id, "content": "Transcription not available"}

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # requires OpenAI Realtime API Access
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
PORT = int(os.getenv('PORT', 5050))

SYSTEM_MESSAGE = (
    "You are an empathetic and non-judgmental AI accountability buddy supporting users in addiction recovery. "
    "Your role is to facilitate daily reflection based on recovery principles, primarily the 10th Step and related self-examination questions. "
    "Maintain a supportive, encouraging, and calm tone. Avoid giving medical advice or acting as a therapist. "
    "You will guide the user through specific questions for either a morning check-in (focused on intention and planning) "
    "or an evening review (focused on reflection and inventory). Listen patiently to their responses. "
    "Your goal is to help them create a reflective journal entry through this structured conversation."
)
VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'response.content.done', 'rate_limits.updated', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created',
    'response.text.delta', 'response.content.part', 'response.text.done',
    'input_audio_buffer.transcript'
]

app = FastAPI()

# Add CORS middleware 
origins = [
    "http://localhost:3000",  # Allow your local frontend
    "http://127.0.0.1:3000", # Alternative local address
    "https://callingbuddy.onrender.com", # Allow the deployed frontend/backend itself
    # Add any other origins if needed, e.g., your deployed frontend URL if different
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

# Initialize Twilio client for outbound calls
# twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None

# Global mapping to track call and stream SIDs
call_mapping = {
    'call_sid_to_info': {},   # Maps Twilio call SID to call info
    'stream_sid_to_call_sid': {},  # Maps Stream SID to Twilio call SID
    'call_id_to_sid': {},  # Maps call ID to Twilio call SID
    'call_id_to_info': {}  # Maps call ID to call info
}

# --- Pydantic Models ---
class CallUserRequest(BaseModel):
    phone_number: str
    call_type: str = Field(..., pattern="^(morning|evening)$") # Enforce morning or evening

# --- Define Question Sets ---
MORNING_QUESTIONS = [
    "Good morning! How are you feeling as you start your day?",
    "Let's start by focusing on your recovery. What's one commitment you're making to your sobriety or well-being today?",
    "What's one specific, positive action you plan to take today that supports that commitment?",
    "Are there any situations, feelings, or triggers you anticipate might be challenging today?",
    "If those challenges arise, what's one coping skill or support you plan to use?",
    "What's one small thing you're grateful for this morning?",
    "Okay, sounds like a plan. Remember your commitment and the tools you have. You've got this. I'll check in with you tonight."
]

EVENING_QUESTIONS = [
    "Welcome back. How was your day overall?",
    # Note: We need to dynamically insert the morning commitment/action/challenge here later.
    "Let's review the day. Thinking about it honestly, where might you have been selfish, dishonest, or afraid?",
    "Did anything happen where an apology might be needed, even if just to yourself?",
    "What did you do today, big or small, to actively strengthen your recovery?",
    "Reflecting honestly, were there any specific problem behaviors you noticed in yourself today?",
    "What's one thing you learned about yourself or your recovery process today?",
    "What are you grateful for as you look back on the day?",
    "Was there anything else about the day, positive or negative, that you feel is important to acknowledge?",
    "Thanks for sharing honestly. Taking this time to reflect is a huge part of the process. Get some rest, and I'll connect with you in the morning."
]

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@app.post("/call-user")
async def call_user(request_body: CallUserRequest):
    """Initiates a virtual call session, creating necessary records but NOT making a phone call."""
    phone_number = request_body.phone_number
    call_type = request_body.call_type
    logger.info(f"Initiating VIRTUAL {call_type} session for {phone_number}")
    
    user = await get_user_by_phone(phone_number)
    if not user:
        # Consider adding error handling if user creation fails
        user = await create_user(phone=phone_number) 
        logger.info(f"Created new user with ID: {user['id']}")
    else:
        logger.info(f"Found existing user with phone {phone_number}")
        
    # Create a call record to track the session
    try:
        call = await create_call(
            user_id=user['id'], 
            status='session_initiated', # New status indicating virtual session start
            call_type=call_type 
        )
        call_record_id = call['id']
        logger.info(f"Created call record with ID {call_record_id}")

        # --- TWILIO CALL REMOVED --- 
        # No longer making a Twilio call here.
        # We still store basic info in mapping for the WebSocket to find later
        # Note: We don't have a Twilio Call SID anymore.
        # We might need to adjust how the websocket finds context later.
        # For now, let's store based on call_record_id if possible or adjust mapping.
        # Maybe the frontend sends call_record_id directly to websocket?
        
        # Store mapping info needed for WebSocket context
        # Storing by call_record_id might be better now
        call_mapping['call_id_to_info'] = call_mapping.get('call_id_to_info', {}) # Ensure exists
        call_mapping['call_id_to_info'][call_record_id] = {
            'user_id': user['id'], 
            'call_type': call_type,
            'timestamp': datetime.datetime.now().timestamp()
            # Removed 'call_sid'
        }
        logger.info(f"Stored session info for call record ID {call_record_id}")
        
        # Return the call_record_id needed by the frontend to connect WebSocket
        return {
            "message": f"Virtual {call_type.capitalize()} session initiated for {phone_number}", 
            "call_record_id": call_record_id
        }
        
    except Exception as e:
        logger.error(f"Error creating call record or mapping: {e}")
        # Attempt to update status to failed if call record was created
        if 'call_record_id' in locals():
           try: 
               await update_call(call_id=call_record_id, status='failed')
           except Exception as update_err:
               logger.error(f"Failed to update call status to failed: {update_err}")
        return JSONResponse(status_code=500, content={"error": f"Failed to initiate virtual session: {str(e)}"}) 

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket, call_record_id: str = None):
    """Handle WebSocket connections directly from the frontend for virtual calls."""
    await websocket.accept()
    logger.info(f"Frontend client connected to media stream for call_record_id: {call_record_id}")
    
    if not call_record_id:
        logger.error("Missing call_record_id query parameter. Closing connection.")
        await websocket.close(code=1008, reason="Missing call_record_id")
        return
        
    # Retrieve call info using call_record_id from the mapping
    call_info = call_mapping.get('call_id_to_info', {}).get(call_record_id)
    if not call_info:
        logger.error(f"Could not find call info for call_record_id {call_record_id}. Closing connection.")
        await websocket.close(code=1008, reason="Invalid call_record_id")
        return
        
    call_type = call_info.get('call_type', 'unknown')
    user_id = call_info.get('user_id')
    logger.info(f"Session started for User: {user_id}, Call Type: {call_type}")

    # Update call status to active
    await update_call(call_id=call_record_id, status='active')

    full_transcription = []
    websocket_closed = False
    current_question_index = 0
    awaiting_answer = False 
    stream_sid = f"frontend_ws_{call_record_id}" # Create a unique ID for logging/mapping if needed
    
    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        await send_session_update(openai_ws) # Ensure this includes transcription config
        
        # Ask the first question immediately upon connection
        await ask_next_question(openai_ws, call_type, current_question_index)
        awaiting_answer = True # Expecting user to potentially speak first

        async def process_frontend_message(message_data):
            """Process messages coming FROM Frontend (audio)."""
            nonlocal awaiting_answer
            # Expecting JSON like: { "event": "media", "audio": "base64..." } 
            if message_data.get('event') == 'media' and 'audio' in message_data and openai_ws.open:
                logger.debug("Received audio chunk from frontend")
                audio_append = {
                    "type": "input_audio_buffer.append",
                    "audio": message_data['audio'] # Expecting base64 string
                }
                await openai_ws.send(json.dumps(audio_append))
                # Don't set awaiting_answer here, let OpenAI's transcript event handle it
            else:
                logger.warning(f"Received unexpected message from frontend: {message_data}")

        async def process_openai_response(response_data):
            """Process responses coming FROM OpenAI (text, audio, events)."""
            nonlocal full_transcription, current_question_index, awaiting_answer
            current_ai_speech_transcript = "" 
            
            # --- Capture AI Speech Transcription --- 
            if response_data['type'] == 'response.audio_transcript.delta' and 'delta' in response_data:
                delta = response_data.get('delta', '')
                logger.info(f"AI SPEECH TRANSCRIPT (delta): '{delta}'")
                if delta:
                    current_ai_speech_transcript += delta
            
            elif response_data['type'] == 'response.audio_transcript.done' and current_ai_speech_transcript:
                final_transcript = response_data.get('transcript', current_ai_speech_transcript).strip()
                logger.info(f"AI SPEECH TRANSCRIPT COMPLETED: '{final_transcript}'")
                if final_transcript:
                    full_transcription.append(f"AI: {final_transcript}")
                current_ai_speech_transcript = "" 
            
            # --- Capture User Speech Transcription --- 
            elif response_data['type'] == 'conversation.item.input_audio_transcription.completed' and 'transcript' in response_data:
                transcript = response_data.get('transcript', '')
                logger.info(f"USER TRANSCRIPT (completed): '{transcript}'")
                
                if transcript and transcript.strip(): 
                    # Filter common noise/short utterances if needed
                    if len(transcript.strip()) < 3 or transcript.strip().lower() in ["you", "bye", "hello", "uh", "um"]:
                        logger.warning(f"Discarding likely inaccurate short user transcript: '{transcript.strip()}'")
                    else:
                        message = f"User: {transcript.strip()}"
                        full_transcription.append(message)
                        logger.info(f"Added user message: '{message}'")
                        
                        # User has answered, move to next question
                        awaiting_answer = False # No longer waiting for this answer
                        current_question_index += 1
                        await ask_next_question(openai_ws, call_type, current_question_index)
                        awaiting_answer = True # Now waiting for answer to the *new* question

            # --- Send Audio to Frontend --- 
            elif response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                # We need to send audio back to the frontend client
                audio_b64 = response_data['delta']
                logger.debug("Sending audio chunk to frontend")
                audio_message = {
                    "event": "audio",
                    "audio": audio_b64
                }
                await websocket.send_json(audio_message) # Send direct to frontend WS
            
            # Other events (session.updated, etc.) - log if needed
            elif response_data['type'] == 'session.updated':
                 logger.info("Session updated successfully")
            elif response_data['type'] == 'response.done':
                 logger.info("OpenAI response.done received")
                 # After AI finishes speaking the question, we are definitely waiting for an answer
                 awaiting_answer = True 

        # --- Main Loop --- 
        frontend_task = asyncio.create_task(frontend_message_processor(websocket, process_frontend_message))
        openai_task = asyncio.create_task(openai_response_processor(openai_ws, process_openai_response))
        
        done, pending = await asyncio.wait(
            [frontend_task, openai_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        websocket_closed = True
        for task in pending:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        
        # Final cleanup and saving
        logger.info(f"WebSocket session ending for call_record_id: {call_record_id}")
        save_final_transcription(full_transcription, call_record_id, call_mapping) # Pass call_record_id

        if openai_ws.open:
            await openai_ws.close()
        if websocket.client_state == websockets.protocol.State.OPEN:
             await websocket.close(code=1000)

# --- Helper Functions --- 
async def frontend_message_processor(websocket: WebSocket, callback):
    """Handles receiving messages from Frontend WebSocket."""
    try:
        async for message in websocket.iter_text():
            await callback(json.loads(message))
    except WebSocketDisconnect:
        logger.info("Frontend WebSocket disconnected.")
    except Exception as e:
        logger.error(f"Error receiving from Frontend: {e}")

async def openai_response_processor(openai_ws: websockets.WebSocketClientProtocol, callback):
    """Handles receiving messages from OpenAI."""
    try:
        async for message in openai_ws:
            await callback(json.loads(message))
    except websockets.exceptions.ConnectionClosedOK:
        logger.info("OpenAI WebSocket closed normally.")
    except Exception as e:
        logger.error(f"Error receiving from OpenAI: {e}")

async def ask_next_question(openai_ws, call_type, index):
    """Instructs the AI to ask the next question in the sequence."""
    question = None
    if call_type == "morning" and index < len(MORNING_QUESTIONS):
        question = MORNING_QUESTIONS[index]
    elif call_type == "evening" and index < len(EVENING_QUESTIONS):
        question = EVENING_QUESTIONS[index]
        # TODO: Inject morning context for specific evening questions later
    
    if question:
        logger.info(f"Asking AI to pose question {index+1} ({call_type}): '{question}'")
        # Send a message to OpenAI to make it speak the question
        # We use conversation.item.create to inject an assistant message asking the question
        create_item_event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "assistant",
                "content": [{
                    "type": "text",
                    "text": question
                }]
            }
        }
        try:
            await openai_ws.send(json.dumps(create_item_event))
            # Optionally trigger response immediately if desired, or let AI handle it
            # response_create_event = {"type": "response.create"} 
            # await openai_ws.send(json.dumps(response_create_event))
        except Exception as e:
            logger.error(f"Error sending question instruction to OpenAI: {e}")
    else:
        logger.info(f"Reached end of {call_type} questions.")
        # Optionally send a concluding message or close the call

def save_final_transcription(transcription_list, call_record_id, call_mapping):
    """Saves the final transcription list to file and database using call_record_id."""
    if not transcription_list:
        logger.warning("No transcription data captured during the call.")
        return
        
    logger.info(f"--- FINAL TRANSCRIPTION --- ({len(transcription_list)} messages)")
    # Assemble the final transcript text
    # Remove duplicates? (May not be needed if captured correctly)
    seen = set()
    unique_transcription = []
    for item in transcription_list:
        if item not in seen:
            seen.add(item)
            unique_transcription.append(item)
            
    transcription_text = "\n".join(unique_transcription)
    for line in unique_transcription: # Log final transcript line-by-line
        logger.info(line)
    logger.info(f"--- END FINAL TRANSCRIPTION ---")

    # Save to file (using call_record_id in filename might be useful)
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"transcription_{call_record_id}_{timestamp}.txt"
        with open(filename, "w") as f:
            f.write(transcription_text)
        logger.info(f"Saved transcription to file: {filename}")
    except Exception as file_error:
        logger.error(f"Could not save transcription to file: {file_error}")

    # Save to Supabase
    if supabase_available:
        try:
            if not call_record_id:
                 logger.warning("Missing call_record_id for saving transcription to database.")
                 return 

            logger.info(f"Attempting to save transcription to database for call ID: {call_record_id}")
            # Ensure DB functions are async or run appropriately
            asyncio.create_task(create_transcription(call_id=call_record_id, content=transcription_text))
            asyncio.create_task(update_call(
                call_id=call_record_id, 
                status="completed",
                ended_at=datetime.datetime.now().isoformat()
            ))
            logger.info(f"Database save tasks created for call ID: {call_record_id}")
        except Exception as db_error:
            logger.error(f"Failed to save transcription to database: {db_error}")

async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
            "input_audio_transcription": {  # Explicitly enable transcription
                "model": "whisper-1",       # Or another suitable model if needed
                "language": "en"            # Specify language
            }
        }
    }
    logger.info('Sending session update to OpenAI with transcription enabled')
    await openai_ws.send(json.dumps(session_update))

# New endpoints for working with transcriptions
@app.get("/calls/{call_id}/transcription")
async def get_call_transcription(call_id: str):
    """Get the transcription for a specific call."""
    try:
        transcription = await get_transcription_by_call_id(call_id)
        if not transcription:
            return JSONResponse(
                status_code=404,
                content={"error": "Transcription not found for this call"}
            )
        
        return JSONResponse(
            status_code=200,
            content=transcription
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error retrieving transcription: {str(e)}"}
        )

@app.get("/health")
async def health_check():
    """Endpoint to check the health of the application and its connections."""
    health = {
        "status": "healthy",
        "timestamp": str(asyncio.get_event_loop().time()),
        "services": {
            "twilio": "available" if twilio_client else "unavailable",
            "supabase": "available" if supabase_available else "unavailable"
        },
        "config": {
            "openai_api_key": "configured" if OPENAI_API_KEY else "missing",
            "twilio_account_sid": "configured" if TWILIO_ACCOUNT_SID else "missing",
            "twilio_auth_token": "configured" if TWILIO_AUTH_TOKEN else "missing",
            "twilio_phone_number": "configured" if TWILIO_PHONE_NUMBER else "missing",
            "supabase_url": "configured" if os.getenv("SUPABASE_URL") else "missing",
            "supabase_key": "configured" if os.getenv("SUPABASE_SERVICE_ROLE_KEY") else "missing"
        }
    }
    
    return JSONResponse(content=health)

@app.get("/debug-supabase")
async def debug_supabase():
    """Special endpoint to test Supabase connection directly."""
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    
    results = {
        "supabase_url": supabase_url,
        "service_key_length": len(service_key) if service_key else 0,
        "anon_key_length": len(anon_key) if anon_key else 0,
        "direct_api_tests": []
    }
    
    # Try direct REST API call with service key
    if supabase_url and service_key:
        try:
            headers = {
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}"
            }
            test_url = f"{supabase_url}/rest/v1/users?limit=1"
            response = requests.get(test_url, headers=headers, timeout=10)
            results["direct_api_tests"].append({
                "key_type": "service_role",
                "url": test_url,
                "status_code": response.status_code,
                "response": response.text[:500]  # Truncate long responses
            })
        except Exception as e:
            results["direct_api_tests"].append({
                "key_type": "service_role",
                "url": test_url if 'test_url' in locals() else "not set",
                "error": str(e)
            })
    
    # Try direct REST API call with anon key
    if supabase_url and anon_key:
        try:
            headers = {
                "apikey": anon_key,
                "Authorization": f"Bearer {anon_key}"
            }
            test_url = f"{supabase_url}/rest/v1/users?limit=1"
            response = requests.get(test_url, headers=headers, timeout=10)
            results["direct_api_tests"].append({
                "key_type": "anon",
                "url": test_url,
                "status_code": response.status_code,
                "response": response.text[:500]  # Truncate long responses
            })
        except Exception as e:
            results["direct_api_tests"].append({
                "key_type": "anon",
                "url": test_url if 'test_url' in locals() else "not set",
                "error": str(e)
            })
    
    return JSONResponse(content=results)

@app.get("/debug-key-format")
async def debug_key_format():
    """Endpoint to check the format of API keys without revealing them."""
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    
    results = {
        "service_key": {
            "length": len(service_key),
            "first_10_chars": service_key[:10] if service_key else "",
            "last_10_chars": service_key[-10:] if len(service_key) >= 10 else "",
            "starts_with_eyJ": service_key.startswith("eyJ") if service_key else False,
            "contains_newlines": "\n" in service_key,
            "contains_spaces": " " in service_key,
            "contains_quotes": "\"" in service_key or "'" in service_key,
            "common_format": bool(service_key.startswith("eyJ") and "." in service_key and len(service_key) > 100) if service_key else False
        },
        "anon_key": {
            "length": len(anon_key),
            "first_10_chars": anon_key[:10] if anon_key else "",
            "last_10_chars": anon_key[-10:] if len(anon_key) >= 10 else "",
            "starts_with_eyJ": anon_key.startswith("eyJ") if anon_key else False,
            "contains_newlines": "\n" in anon_key,
            "contains_spaces": " " in anon_key,
            "contains_quotes": "\"" in anon_key or "'" in anon_key,
            "common_format": bool(anon_key.startswith("eyJ") and "." in anon_key and len(anon_key) > 100) if anon_key else False
        }
    }
    
    return JSONResponse(content=results)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT) 