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
    "You are a helpful and bubbly AI assistant who loves to chat about "
    "anything the user is interested in and is prepared to offer them facts. "
    "You have a penchant for dad jokes, owl jokes, and rickrolling – subtly. "
    "Always stay positive, but work in a joke when appropriate."
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

# Add CORS middleware to allow requests from the mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your app's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

# Initialize Twilio client for outbound calls
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None

# Global mapping to track call and stream SIDs
call_mapping = {
    'call_sid_to_info': {},   # Maps Twilio call SID to call info
    'stream_sid_to_call_sid': {}  # Maps Stream SID to Twilio call SID
}

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    # Log raw request information for debugging
    logger.info(f"Incoming call request: method={request.method}, headers={request.headers}")
    
    # For Twilio calls, we'll proceed without requiring the CallSid
    # The important part is returning valid TwiML
    
    # Build the TwiML response
    response = VoiceResponse()
    
    # <Say> punctuation to improve text-to-speech flow
    response.say("Please wait while we connect your call.")
    response.pause(length=1)
    response.say("OK you can start talking!")
    
    # Create the connection
    host = request.url.hostname
    connect = Connect()
    
    # Simple stream URL without parameters
    stream_url = f'wss://{host}/media-stream'
    
    # Log the stream URL
    logger.info(f"Creating stream connection to: {stream_url}")
    
    # Add the stream to the Connect verb
    connect.stream(url=stream_url)
    response.append(connect)
    
    # Return the TwiML
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.post("/call-user")
async def call_user(request: Request):
    """Initiate an outbound call to the user's phone number."""
    try:
        # Parse the request body
        data = await request.json()
        to_number = data.get('to')
        
        if not to_number:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing 'to' parameter with the phone number to call"}
            )
            
        if not twilio_client:
            return JSONResponse(
                status_code=500,
                content={"error": "Twilio client not configured. Check your environment variables."}
            )
            
        logger.info(f"Initiating call to {to_number}")
        
        try:
            # Check if user exists, create if not
            user = await get_user_by_phone(to_number)
            if not user:
                user = await create_user(phone_number=to_number)
                logger.info(f"Created new user with phone {to_number}")
            else:
                logger.info(f"Found existing user with phone {to_number}")
                
            # Create a call record in the database
            db_call = await create_call(user_id=user['id'], status="initiated")
            logger.info(f"Created call record with ID {db_call['id']}")
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            logger.warning("Proceeding with call despite database error")
            # Create dummy objects to allow the call to proceed
            user = {"id": "dummy-user-id", "phone_number": to_number}
            db_call = {"id": "dummy-call-id", "user_id": user['id']}
        
        # Create the URL for the TwiML that will be executed when the call connects
        callback_url = f"https://{request.url.hostname}/incoming-call"
        
        # Make the call
        call = twilio_client.calls.create(
            to=to_number,
            from_=TWILIO_PHONE_NUMBER,
            url=callback_url,
            method="POST"
        )
        
        logger.info(f"Twilio call initiated with SID {call.sid}")
        
        # Update the call record with Twilio's call SID if we have a real db call
        try:
            if db_call['id'] != "dummy-call-id":
                # Now we can include call_sid as the parameter is supported
                await update_call(call_id=db_call['id'], status="initiated", call_sid=call.sid)
                logger.info(f"Updated call record with Twilio SID {call.sid}")
                
                # Store the call SID for later use in the WebSocket handler
                # We'll use this to associate the stream with the call record
                call_mapping['call_sid_to_info'][call.sid] = {
                    'call_id': db_call['id'],
                    'user_id': user['id'],
                    'timestamp': asyncio.get_event_loop().time()
                }
                logger.info(f"Added call SID {call.sid} to mapping for future reference")
        except Exception as update_error:
            logger.error(f"Failed to update call record: {update_error}")
        
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Call initiated", "call_sid": call.sid, "call_id": db_call['id']}
        )
    except Exception as e:
        logger.error(f"Failed to initiate call: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to initiate call: {str(e)}"}
        )

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    logger.info("Client connected to media stream")
    await websocket.accept()
    
    # Variables to track the call and collect transcription
    stream_sid = None
    full_transcription = []
    websocket_closed = False
    
    # Create a timestamp for this session
    session_timestamp = asyncio.get_event_loop().time()
    logger.info(f"Starting new session at timestamp: {session_timestamp}")
    
    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        await send_session_update(openai_ws)
        
        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
            nonlocal stream_sid, websocket_closed
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'media' and openai_ws.open:
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        
                        # Send ONLY to conversation API 
                        await openai_ws.send(json.dumps(audio_append))
                        
                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        logger.info(f"Incoming stream has started {stream_sid}")
                        
                        # Try to associate this stream with a call
                        # In Twilio, the CallSid is part of the parameters sent when the stream starts
                        try:
                            if 'start' in data and 'callSid' in data['start']:
                                call_sid = data['start']['callSid']
                                logger.info(f"Found Call SID {call_sid} in stream start event")
                                
                                # Add to our reverse mapping
                                call_mapping['stream_sid_to_call_sid'][stream_sid] = call_sid
                                logger.info(f"Associated stream {stream_sid} with call {call_sid}")
                        except Exception as mapping_error:
                            logger.error(f"Error mapping stream to call: {mapping_error}")
            except WebSocketDisconnect:
                logger.info("Client disconnected from media stream")
                websocket_closed = True
            except Exception as e:
                logger.error(f"Error in receive_from_twilio: {e}")
                websocket_closed = True
            finally:
                # Always mark the WebSocket as closed when this task exits
                websocket_closed = True
                
        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid, full_transcription, websocket_closed
            current_ai_speech_transcript = "" # Accumulate AI speech transcript deltas
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    
                    # Log all response types - better for debugging
                    logger.info(f"OpenAI event: {response['type']}")
                    
                    # --- Capture AI Speech Transcription --- 
                    # Accumulate AI speech transcript deltas
                    if response['type'] == 'response.audio_transcript.delta' and 'delta' in response:
                        delta = response.get('delta', '')
                        logger.info(f"AI SPEECH TRANSCRIPT (delta): '{delta}'")
                        if delta:
                            current_ai_speech_transcript += delta
                    
                    # Finalize AI speech transcript when done
                    elif response['type'] == 'response.audio_transcript.done' and current_ai_speech_transcript:
                        final_transcript = response.get('transcript', current_ai_speech_transcript).strip()
                        logger.info(f"AI SPEECH TRANSCRIPT COMPLETED: '{final_transcript}'")
                        if final_transcript: # Avoid adding empty messages
                            full_transcription.append(f"AI: {final_transcript}")
                        current_ai_speech_transcript = "" # Reset accumulator

                    # --- Capture User Speech Transcription --- 
                    # Use the completed event for user speech transcription
                    elif response['type'] == 'conversation.item.input_audio_transcription.completed' and 'transcript' in response:
                        transcript = response.get('transcript', '')
                        logger.info(f"USER TRANSCRIPT (completed): '{transcript}'")
                        
                        if transcript and transcript.strip(): # Avoid adding empty messages
                            # Filter common noise/short utterances if needed
                            if len(transcript.strip()) < 3 or transcript.strip().lower() in ["you", "bye", "hello", "uh", "um"]:
                                logger.warning(f"Discarding likely inaccurate short user transcript: '{transcript.strip()}'")
                            else:
                                message = f"User: {transcript.strip()}"
                                full_transcription.append(message)
                                logger.info(f"Added user message: '{message}'")
                    
                    # --- Session/Control Events --- 
                    elif response['type'] == 'session.updated':
                        logger.info("Session updated successfully")
                        
                    # --- Send Audio to Twilio --- 
                    elif response['type'] == 'response.audio.delta' and response.get('delta'):
                        # Audio from OpenAI
                        try:
                            if not websocket_closed:
                                audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                                audio_delta = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": audio_payload
                                    }
                                }
                                await websocket.send_json(audio_delta)
                        except Exception as e:
                            if "websocket.close" in str(e) or "already completed" in str(e):
                                # Connection was closed, mark it
                                websocket_closed = True
                                logger.info("WebSocket closed, stopping audio transmission")
                            else:
                                logger.error(f"Error processing audio data: {e}")
            except Exception as e:
                logger.error(f"Error in send_to_twilio: {e}")
                
                # Log the transcription even if we can't save it properly
                if full_transcription:
                    transcription_text = "\n".join(full_transcription)
                    logger.info(f"Error occurred. Transcription so far ({len(full_transcription)} messages):")
                    logger.info(f"--- TRANSCRIPTION START ---")
                    logger.info(transcription_text)
                    logger.info(f"--- TRANSCRIPTION END ---")

        # Start both tasks and wait for them to complete
        twilio_receiver = asyncio.create_task(receive_from_twilio())
        openai_sender = asyncio.create_task(send_to_twilio())
        
        done, pending = await asyncio.wait(
            [twilio_receiver, openai_sender],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel any pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
        # Clean up and save the transcription
        # Use ONLY full_transcription list
        if full_transcription:
            # Remove logic related to transcription_service.buffer
            # Remove logic related to processing final continuous transcription
            
            # Log the available transcriptions for debugging
            logger.info(f"--- REAL-TIME TRANSCRIPTION (FINAL) ---")
            for idx, msg in enumerate(full_transcription):
                logger.info(f"[{idx}] {msg}")
            logger.info(f"--- END REAL-TIME TRANSCRIPTION ---")
            
            # Assemble the final transcript (already contains User and AI messages)
            final_transcription = full_transcription # It's already combined
            
            # Remove duplicates while preserving order
            seen = set()
            unique_transcription = []
            for item in final_transcription:
                # Simple check to combine potential fragmented AI messages if needed
                # (More sophisticated merging could be added if needed)
                if item not in seen:
                    seen.add(item)
                    unique_transcription.append(item)
            
            transcription_text = "\n".join(unique_transcription)
            
            # Store in global variable for force-save endpoint
            try:
                global last_transcription_text, last_call_sid
                last_transcription_text = transcription_text
                if stream_sid in call_mapping['stream_sid_to_call_sid']:
                    last_call_sid = call_mapping['stream_sid_to_call_sid'][stream_sid]
            except Exception as e:
                logger.error(f"Error storing global transcription: {e}")
            
            logger.info(f"Call ended. Transcription ({len(unique_transcription)} messages):")
            logger.info(f"--- TRANSCRIPTION START ---")
            logger.info(transcription_text)
            logger.info(f"--- TRANSCRIPTION END ---")
            
            # Save to a file as a fallback option
            try:
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"transcription_{timestamp}.txt"
                
                with open(filename, "w") as f:
                    f.write(transcription_text)
                
                logger.info(f"Saved transcription to file: {filename}")
            except Exception as file_error:
                logger.error(f"Could not save transcription to file: {file_error}")
            
            # Try to save to Supabase if possible
            if supabase_available:
                try:
                    # Try to find the matching call for this stream
                    call_id = None
                    
                    # First check if we have a direct stream to call mapping
                    if stream_sid and stream_sid in call_mapping['stream_sid_to_call_sid']:
                        call_sid = call_mapping['stream_sid_to_call_sid'][stream_sid]
                        logger.info(f"Found call SID {call_sid} for stream {stream_sid}")
                        
                        if call_sid in call_mapping['call_sid_to_info']:
                            call_info = call_mapping['call_sid_to_info'][call_sid]
                            call_id = call_info['call_id']
                            logger.info(f"Found call record ID {call_id} for call SID {call_sid}")
                    
                    # If no direct mapping, try the most recent call
                    if not call_id:
                        recent_calls = []
                        for call_sid, call_info in call_mapping['call_sid_to_info'].items():
                            if 'call_id' in call_info and call_info['call_id'] != "dummy-call-id":
                                recent_calls.append((call_info.get('timestamp', 0), call_info))
                        
                        if recent_calls:
                            # Sort by timestamp and get the most recent
                            recent_calls.sort(key=lambda x: x[0])
                            call_info = recent_calls[-1][1]
                            call_id = call_info['call_id']
                            logger.info(f"Using most recent call with ID: {call_id}")
                    
                    if call_id:
                        # Save the transcription
                        transcription = await create_transcription(
                            call_id=call_id,
                            content=transcription_text
                        )
                        
                        # Update the call record
                        import datetime
                        await update_call(
                            call_id=call_id, 
                            status="completed",
                            ended_at=datetime.datetime.now().isoformat()
                        )
                        
                        logger.info(f"Saved transcription to database for call ID: {call_id}")
                    else:
                        logger.warning("No matching call found in our mapping - transcription not saved to database")
                except Exception as db_error:
                    logger.error(f"Failed to save transcription to database: {db_error}")
        else:
             logger.warning("No transcription data captured during the call.")
        
        # Make sure everything is closed
        if openai_ws.open:
            await openai_ws.close()

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