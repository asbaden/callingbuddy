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
    call_type: str = Field(..., pattern="^(morning|evening)$") 

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

# --- CONSTANTS ---
TEST_USER_PHONE = "+10000000000" # Define a placeholder phone for the test user

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@app.post("/call-user")
async def call_user(request_body: CallUserRequest):
    """Initiates a virtual call session for testing, using a placeholder user."""
    call_type = request_body.call_type
    logger.info(f"Initiating VIRTUAL {call_type} session (Test User Mode)")
    
    # --- Use or Create a Test User --- 
    test_user_id = None
    try:
        test_user = await get_user_by_phone(TEST_USER_PHONE)
        if not test_user:
            logger.info(f"Creating placeholder test user ({TEST_USER_PHONE})...")
            test_user = await create_user(phone_number=TEST_USER_PHONE, name="Test User") 
            if test_user and test_user.get('id') != "dummy-user-id": # Check if creation was real
                 logger.info(f"Created test user with ID: {test_user['id']}")
                 test_user_id = test_user['id']
            else:
                 logger.error(f"Failed to create placeholder test user.")
                 # Handle error - perhaps raise exception or return error response?
                 raise Exception("Failed to create necessary test user record")
        else:
            logger.info(f"Found existing test user with ID: {test_user['id']}")
            test_user_id = test_user['id']
            
        if not test_user_id:
             raise Exception("Could not obtain a valid ID for the test user.")
             
    except Exception as user_err:
        logger.error(f"Error getting or creating test user: {user_err}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Failed to set up test user for session."}) 
    # --- End Test User Logic --- 
        
    # Create a call record to track the session
    try:
        call = await create_call(
            user_id=test_user_id, # Use the valid test user ID
            status='session_initiated', 
            call_type=call_type 
        )
        # Check if call creation actually succeeded (might return None on DB error)
        if not call:
             logger.error("Failed to create call record in database (create_call returned None).")
             # Try to get more details if possible from logs
             raise Exception("Database operation failed during call creation.")
             
        call_record_id = call['id']
        logger.info(f"Created call record with ID {call_record_id} for Test User {test_user_id}")

        # Store minimal mapping info needed for WebSocket context
        call_mapping['call_id_to_info'] = call_mapping.get('call_id_to_info', {}) # Ensure exists
        call_mapping['call_id_to_info'][call_record_id] = {
            'user_id': test_user_id, 
            'call_type': call_type,
            'timestamp': datetime.datetime.now().timestamp()
        }
        logger.info(f"Stored session info for call record ID {call_record_id}")
        
        # Return the real call_record_id needed by the frontend
        return {
            "message": f"Virtual {call_type.capitalize()} session initiated (Test User)", 
            "call_record_id": call_record_id
        }
        
    except Exception as e:
        logger.error(f"Error creating call record or mapping: {e}", exc_info=True)
        # Attempt to update status to failed if call record was created
        # Use the ID obtained *before* the exception, if available
        call_id_to_update = locals().get('call_record_id', None)
        if call_id_to_update:
           try: 
               await update_call(call_id=call_id_to_update, status='failed')
           except Exception as update_err:
               logger.error(f"Failed to update call status to failed: {update_err}")
        return JSONResponse(status_code=500, content={"error": f"Failed to initiate virtual session: {str(e)}"}) 

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket, call_record_id: str = None):
    """Handle WebSocket connections directly from the frontend for virtual calls."""
    await websocket.accept()
    logger.info(f"Frontend client connected for call_record_id: {call_record_id}")
    
    # --- State Initialization --- 
    if not call_record_id:
        logger.error("Missing call_record_id query parameter. Closing connection.")
        await websocket.close(code=1008, reason="Missing call_record_id")
        return
    call_info = call_mapping.get('call_id_to_info', {}).get(call_record_id)
    if not call_info:
        logger.error(f"Could not find call info for call_record_id {call_record_id}. Closing connection.")
        await websocket.close(code=1008, reason="Invalid call_record_id")
        return
    call_type = call_info.get('call_type', 'unknown')
    user_id = call_info.get('user_id')
    await update_call(call_id=call_record_id, status='active')
    logger.info(f"Session started for User: {user_id}, Call Type: {call_type}")

    full_transcription = []
    current_question_index = 0
    awaiting_answer = False 
    current_ai_speech_transcript = "" # Moved state here
    # --- End State Initialization --- 
    
    try:
        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            await send_session_update(openai_ws) 
            await ask_next_question(openai_ws, call_type, current_question_index)
            awaiting_answer = True 

            async def process_frontend_message(message_data):
                if message_data.get('event') == 'media' and 'audio' in message_data and openai_ws.open:
                    logger.debug("Received audio chunk from frontend")
                    audio_append = {
                        "type": "input_audio_buffer.append",
                        "audio": message_data['audio']
                    }
                    await openai_ws.send(json.dumps(audio_append))
                else:
                    logger.warning(f"Received unexpected message from frontend: {message_data}")

            async def process_openai_response(response_data):
                nonlocal full_transcription, current_question_index, awaiting_answer, current_ai_speech_transcript
                
                logger.info(f"OpenAI event: {response_data['type']}")
                # --- Capture AI Speech Transcription --- 
                if response_data['type'] == 'response.audio_transcript.delta' and 'delta' in response_data:
                    delta = response_data.get('delta', '')
                    # logger.info(f"AI SPEECH TRANSCRIPT (delta): '{delta}'") # Can be too verbose
                    if delta:
                        current_ai_speech_transcript += delta
                
                elif response_data['type'] == 'response.audio_transcript.done': # Check type first
                    final_transcript = response_data.get('transcript', current_ai_speech_transcript).strip()
                    logger.info(f"AI SPEECH TRANSCRIPT COMPLETED: '{final_transcript}'")
                    if final_transcript:
                        message = f"AI: {final_transcript}"
                        full_transcription.append(message)
                        # Check state BEFORE sending
                        if websocket.client_state == websockets.protocol.State.OPEN:
                            await send_transcript_to_frontend(websocket, "AI", final_transcript)
                        else:
                            logger.warning("Frontend WS closed before sending AI transcript.")
                    current_ai_speech_transcript = "" # Reset accumulator
                
                # --- Capture User Speech Transcription --- 
                elif response_data['type'] == 'conversation.item.input_audio_transcription.completed' and 'transcript' in response_data:
                    transcript = response_data.get('transcript', '')
                    logger.info(f"USER TRANSCRIPT (completed): '{transcript}'")
                    
                    if transcript and transcript.strip(): 
                        if len(transcript.strip()) < 3 or transcript.strip().lower() in ["you", "bye", "hello", "uh", "um"]:
                            logger.warning(f"Discarding likely inaccurate short user transcript: '{transcript.strip()}'")
                        else:
                            message_text = transcript.strip()
                            message = f"User: {message_text}"
                            full_transcription.append(message)
                            logger.info(f"Added user message: '{message}'")
                            # Check state BEFORE sending
                            if websocket.client_state == websockets.protocol.State.OPEN:
                                await send_transcript_to_frontend(websocket, "User", message_text)
                            else:
                                logger.warning("Frontend WS closed before sending User transcript.")
                            
                            # User has answered, move to next question
                            awaiting_answer = False 
                            current_question_index += 1
                            await ask_next_question(openai_ws, call_type, current_question_index)
                            awaiting_answer = True 

                # --- Send Audio to Frontend --- 
                elif response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                    audio_b64 = response_data['delta']
                    # logger.debug("Sending audio chunk to frontend") # Can be too verbose
                    audio_message = {"event": "audio", "audio": audio_b64}
                    # Check state BEFORE sending
                    if websocket.client_state == websockets.protocol.State.OPEN:
                        # logger.debug("Sending audio chunk to frontend") 
                        await websocket.send_json(audio_message)
                    else:
                        logger.warning("Frontend WS closed before sending audio chunk.")
                
                # --- Other Events --- 
                elif response_data['type'] == 'session.updated':
                    logger.info("Session updated successfully")
                elif response_data['type'] == 'response.done':
                    logger.info("OpenAI response.done received")
                    # Important: We set awaiting_answer=True *only* after AI finishes speaking *a question*
                    # This assumes ask_next_question was the last thing that triggered the response.
                    # If AI speaks unprompted, this logic might need adjustment.
                    # Let's refine: only set awaiting_answer=True if we know AI just asked a question.
                    # We can infer this if the last full_transcription entry was an AI message from MORNING/EVENING lists.
                    # For simplicity now, let's assume response.done for AI means it finished asking the question.
                    awaiting_answer = True 

            # --- Main Loop --- 
            frontend_task = asyncio.create_task(frontend_message_processor(websocket, process_frontend_message))
            openai_task = asyncio.create_task(openai_response_processor(openai_ws, process_openai_response))
            
            # Wait for EITHER task to complete (e.g., one side disconnects or errors)
            done, pending = await asyncio.wait(
                [frontend_task, openai_task],
                return_when=asyncio.FIRST_COMPLETED # Keep this, completion means something ended
            )
            
            # Log which task completed
            for task in done:
                if task == frontend_task:
                    logger.info("Frontend message processor task completed.")
                elif task == openai_task:
                    logger.info("OpenAI response processor task completed.")
                try:
                    # Raise exceptions if tasks failed
                    task.result()
                except Exception as task_exc:
                    logger.error(f"Task completed with error: {task_exc}", exc_info=True)
            
            # Cancel the other task forcefully
            for task in pending:
                logger.info("Cancelling pending task.")
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass
            
    except websockets.exceptions.ConnectionClosed as e:
        logger.warning(f"OpenAI WebSocket connection closed: {e.code} {e.reason}")
    except Exception as e:
        logger.error(f"Error during WebSocket handling: {e}", exc_info=True)
    finally:
        # Final cleanup and saving
        logger.info(f"WebSocket session ending for call_record_id: {call_record_id}")
        # Check which task finished first if possible (difficult with wait)
        if frontend_task.done() and not openai_task.done():
            logger.info("Frontend task finished first.")
        elif openai_task.done() and not frontend_task.done():
             logger.info("OpenAI task finished first.")
        else:
             logger.info("Both tasks finished concurrently or main loop exited.")
             
        save_final_transcription(full_transcription, call_record_id, call_mapping)
        # Ensure websockets are closed even if errors occurred
        try:
            if openai_ws and openai_ws.open:
                await openai_ws.close()
                logger.info("Closed OpenAI WebSocket in finally block.")
        except Exception as ws_close_err:
            logger.error(f"Error closing OpenAI WS in finally: {ws_close_err}")
        try:
            if websocket.client_state == websockets.protocol.State.OPEN:
                await websocket.close(code=1000)
                logger.info("Closed Frontend WebSocket in finally block.")
        except Exception as ws_close_err:
             logger.error(f"Error closing Frontend WS in finally: {ws_close_err}")

# --- Helper Functions --- 
async def frontend_message_processor(websocket: WebSocket, callback):
    """Handles receiving messages from Frontend WebSocket. Runs until disconnect/error."""
    try:
        # Loop indefinitely while the connection is open
        while websocket.client_state == websockets.protocol.State.OPEN:
            try:
                # Wait for a message with a timeout (e.g., 1 second)
                # This prevents blocking forever if no messages arrive but keeps the task alive.
                message = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                logger.debug(f"Received message from frontend: {message[:100]}...")
                await callback(json.loads(message))
            except asyncio.TimeoutError:
                # No message received, just continue looping
                # logger.debug("No message from frontend, still listening...")
                continue
            except websockets.exceptions.ConnectionClosed:
                # Handle explicit close within the loop if wait_for doesn't catch it first
                logger.info("Frontend WebSocket closed during receive.")
                break # Exit the loop cleanly
            except json.JSONDecodeError as json_err:
                 logger.error(f"JSON Decode Error processing Frontend message: {json_err}")
                 logger.error(f"Offending frontend message snippet: {message[:500]}")
            except Exception as inner_e:
                 # Catch errors within the loop's try block
                 logger.error(f"Error processing frontend message: {inner_e}", exc_info=True)
                 # Decide if we should break or continue based on error type
                 # For now, let's continue unless it's fatal

    except websockets.exceptions.ConnectionClosedOK:
        logger.info("Frontend WebSocket disconnected normally (ClosedOK).")
    except websockets.exceptions.ConnectionClosedError as close_err:
        logger.warning(f"Frontend WebSocket closed with error. Code: {close_err.code}, Reason: {close_err.reason}")
    except Exception as e:
        # Catch errors occurring outside the main loop (e.g., during initial setup)
        logger.error(f"Error in frontend_message_processor task: {e}", exc_info=True)
    finally:
        logger.info("frontend_message_processor task finished.")

async def openai_response_processor(openai_ws: websockets.WebSocketClientProtocol, callback):
    """Handles receiving messages from OpenAI."""
    try:
        async for message in openai_ws:
            try:
                # Log raw message for deep debugging if needed
                # logger.debug(f"RAW OpenAI Message: {message}") 
                response_data = json.loads(message)
                await callback(response_data)
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON Decode Error processing OpenAI message: {json_err}")
                logger.error(f"Offending message snippet: {message[:500]}") # Log beginning of bad message
            except Exception as callback_err:
                # Log errors that happen *inside* the process_openai_response function
                logger.error(f"Error in process_openai_response callback: {callback_err}", exc_info=True)
    except websockets.exceptions.ConnectionClosed as close_err:
        # Log specific close codes and reasons
        logger.warning(f"OpenAI WebSocket closed. Code: {close_err.code}, Reason: {close_err.reason}")
    except Exception as e:
        logger.error(f"Unhandled error in openai_response_processor loop: {e}", exc_info=True)
    finally:
        logger.info("openai_response_processor task finished.")

async def ask_next_question(openai_ws, call_type, index):
    """Instructs the AI to ask the next question in the sequence."""
    question = None
    if call_type == "morning" and index < len(MORNING_QUESTIONS):
        question = MORNING_QUESTIONS[index]
    elif call_type == "evening" and index < len(EVENING_QUESTIONS):
        question = EVENING_QUESTIONS[index]
    
    if question:
        logger.info(f"Asking AI to pose question {index+1} ({call_type}): '{question}'")
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
        # Explicitly trigger response generation
        response_create_event = {"type": "response.create"}
        
        try:
            # Send instruction to add the question to context
            await openai_ws.send(json.dumps(create_item_event))
            # Immediately ask AI to generate response (speak the question)
            logger.info("Sending response.create to trigger AI speech")
            await openai_ws.send(json.dumps(response_create_event))
        except Exception as e:
            logger.error(f"Error sending question/response trigger to OpenAI: {e}")
    else:
        logger.info(f"Reached end of {call_type} questions.")
        # TODO: Optionally send a concluding message or close the call

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

# --- NEW HELPER FUNCTION --- 
async def send_transcript_to_frontend(websocket: WebSocket, sender: str, text: str):
    """Sends a transcript line to the connected frontend client."""
    try:
        if websocket.client_state == websockets.protocol.State.OPEN:
            message = {
                "event": "transcript",
                "sender": sender, # "User" or "AI"
                "text": text
            }
            logger.info(f"Sending transcript to frontend: {sender}: {text}")
            await websocket.send_json(message)
        else:
            logger.warning("Attempted to send transcript to closed frontend WebSocket")
    except Exception as e:
        logger.error(f"Error sending transcript to frontend: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT) 