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
    'input_audio_buffer.speech_started', 'session.created'
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

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    # <Say> punctuation to improve text-to-speech flow
    response.say("Please wait while we connect your call.")
    response.pause(length=1)
    response.say("OK you can start talking!")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
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
                await update_call(call_id=db_call['id'], call_sid=call.sid)
                logger.info(f"Updated call record with Twilio SID {call.sid}")
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
    call_record = None
    full_transcription = []
    
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
            nonlocal stream_sid, call_record
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'media' and openai_ws.open:
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        logger.info(f"Incoming stream has started {stream_sid}")
                        
                        # Try to find the call record based on the stream SID
                        # This is a bit tricky since we don't have a direct mapping from stream_sid to call_sid
                        # In a production app, you might want to pass additional parameters or use a different approach
            except WebSocketDisconnect:
                logger.info("Client disconnected from media stream")
                
                # Save the transcription if we have collected any text
                if call_record and full_transcription:
                    try:
                        transcription_text = "\n".join(full_transcription)
                        logger.info(f"Saving transcription of {len(full_transcription)} messages")
                        await create_transcription(
                            call_id=call_record['id'],
                            content=transcription_text
                        )
                        # Update call status to completed
                        await update_call(call_id=call_record['id'], status="completed")
                    except Exception as e:
                        logger.error(f"Error saving transcription: {e}")
                
                if openai_ws.open:
                    await openai_ws.close()

        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid, full_transcription
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    
                    # Log important events
                    if response['type'] in LOG_EVENT_TYPES:
                        logger.info(f"Received event: {response['type']}")
                    
                    # Record transcribed text
                    if response['type'] == 'response.content.part' and 'content' in response:
                        message = f"AI: {response['content']}"
                        full_transcription.append(message)
                        logger.debug(f"AI message: {response['content']}")
                    elif response['type'] == 'input_audio_buffer.transcript' and 'transcript' in response:
                        message = f"User: {response['transcript']}"
                        full_transcription.append(message)
                        logger.debug(f"User message: {response['transcript']}")
                        
                    if response['type'] == 'session.updated':
                        logger.info("Session updated successfully")
                        
                    if response['type'] == 'response.audio.delta' and response.get('delta'):
                        # Audio from OpenAI
                        try:
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
                            logger.error(f"Error processing audio data: {e}")
            except Exception as e:
                logger.error(f"Error in send_to_twilio: {e}")
                
                # Try to save any collected transcription before exiting
                if call_record and full_transcription:
                    try:
                        transcription_text = "\n".join(full_transcription)
                        logger.info(f"Saving transcription on error: {len(full_transcription)} messages")
                        await create_transcription(
                            call_id=call_record['id'],
                            content=transcription_text
                        )
                    except Exception as save_error:
                        logger.error(f"Error saving transcription on error: {save_error}")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())

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
        }
    }
    logger.info('Sending session update to OpenAI')
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT) 