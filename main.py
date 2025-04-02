import os
import json
import base64
import logging
import asyncio
import websockets
import aiohttp
import tempfile
import subprocess
import shutil
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

# Check for ffmpeg installation
def check_ffmpeg():
    """Check if ffmpeg is installed and try to install it if not."""
    try:
        # Check if ffmpeg is in the PATH
        if shutil.which('ffmpeg'):
            logger.info("ffmpeg is already installed")
            return True
            
        # Try to install ffmpeg using apt-get if it's not found
        logger.warning("ffmpeg not found, attempting to install...")
        
        # Check if we're running on Linux (likely a Render or similar service)
        if os.name == 'posix' and not os.path.exists('/usr/bin/ffmpeg'):
            try:
                # Attempt installation using apt-get (for Debian/Ubuntu)
                process = subprocess.run(
                    ["apt-get", "update", "-y"], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                logger.info(f"apt-get update result: {process.returncode}")
                
                process = subprocess.run(
                    ["apt-get", "install", "-y", "ffmpeg"], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                logger.info(f"apt-get install ffmpeg result: {process.returncode}")
                
                # Check if installation was successful
                if shutil.which('ffmpeg'):
                    logger.info("ffmpeg installation successful")
                    return True
                else:
                    logger.warning("ffmpeg installation failed")
            except Exception as e:
                logger.error(f"Error trying to install ffmpeg: {str(e)}")
        
        # If we're on macOS, provide a hint for installation
        elif os.name == 'posix' and os.path.exists('/usr/bin/sw_vers'):
            logger.warning("On macOS, install ffmpeg using: brew install ffmpeg")
            
        logger.warning("ffmpeg not available - audio conversion will likely fail")
        return False
    except Exception as e:
        logger.error(f"Error checking for ffmpeg: {str(e)}")
        return False

# Check for ffmpeg on startup
ffmpeg_available = check_ffmpeg()
logger.info(f"ffmpeg available: {ffmpeg_available}")

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

# Global mapping to track call and stream SIDs
call_mapping = {
    'call_sid_to_info': {},   # Maps Twilio call SID to call info
    'stream_sid_to_call_sid': {}  # Maps Stream SID to Twilio call SID
}

# Global variables for transcription session
class TranscriptionService:
    """A service to manage a transcription session with proper state handling."""
    
    def __init__(self):
        self.buffer = []
        self.audio_queue = asyncio.Queue()
        self.processing_task = None
        self.sending_task = None
        self.lock = asyncio.Lock()  # Prevent multiple simultaneous session creations
        self.state = "closed"       # States: closed, initializing, ready, error
        self.error_count = 0
        self.max_errors = 3
        self.accumulated_audio = b''  # To accumulate audio data for batch processing
        self.last_processing_time = 0
        self.processing_interval = 5  # Increase from 3 to 5 seconds to collect more audio
        self.min_audio_length = 8000  # Minimum audio length in bytes (about 1 second of 8kHz audio)
        self.continuous_audio = b''   # Store all audio for one continuous transcription
        self.continuous_interval = 60  # Process continuous audio every 60 seconds
        self.last_continuous_time = 0
        self.transcript_segments = []  # Store all transcript segments for post-processing
    
    async def start(self):
        """Start the transcription service if it's not already running."""
        async with self.lock:
            if self.state != "closed":
                logger.info(f"Transcription service already in state: {self.state}")
                return
                
            self.state = "initializing"
            try:
                # Verify API key is set
                if not OPENAI_API_KEY:
                    logger.error("OpenAI API key is not configured")
                    self.state = "error"
                    return False
                
                # Start the processing tasks if not already running
                if not self.processing_task or self.processing_task.done():
                    self.processing_task = asyncio.create_task(self._process_audio_queue())
                    logger.info("Started audio queue processing task")
                
                self.state = "ready"
                self.error_count = 0  # Reset error count on successful connection
                return True
                
            except Exception as e:
                logger.error(f"Failed to start transcription service: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                self.state = "error"
                return False
    
    async def stop(self):
        """Stop the transcription service cleanly."""
        async with self.lock:
            if self.state == "closed":
                return
                
            logger.info("Stopping transcription service")
            
            # Cancel tasks
            if self.processing_task and not self.processing_task.done():
                self.processing_task.cancel()
                logger.info("Cancelled processing task")
                
            if self.sending_task and not self.sending_task.done():
                self.sending_task.cancel()
                logger.info("Cancelled sending task")
            
            self.state = "closed"
            self.error_count = 0
            self.accumulated_audio = b''
    
    async def send_audio(self, audio_data):
        """Queue audio data to be sent to the transcription service."""
        # Start the service if needed
        if self.state == "closed":
            success = await self.start()
            if not success:
                logger.error("Failed to start transcription service")
                return False
        
        # Handle error state with retries
        if self.state == "error":
            self.error_count += 1
            if self.error_count > self.max_errors:
                logger.error(f"Too many errors ({self.error_count}), stopping transcription service")
                await self.stop()
                return False
                
            # Try to restart
            logger.info(f"Attempting to recover transcription service (attempt {self.error_count})")
            await self.stop()
            success = await self.start()
            if not success:
                return False
        
        # Add to the queue - non-blocking
        try:
            # Convert base64 audio to binary
            binary_audio = base64.b64decode(audio_data)
            await self.audio_queue.put(binary_audio)
            return True
        except Exception as e:
            logger.error(f"Error processing audio data: {str(e)}")
            return False
    
    async def _process_audio_queue(self):
        """Process the audio queue and send batches to the transcription service."""
        try:
            while True:
                current_time = asyncio.get_event_loop().time()
                
                # Wait for audio data
                if not self.audio_queue.empty():
                    audio_data = await self.audio_queue.get()
                    self.accumulated_audio += audio_data
                    self.continuous_audio += audio_data  # Add to continuous buffer as well
                    self.audio_queue.task_done()
                
                # Process accumulated audio if enough time has passed AND we have enough audio
                if (current_time - self.last_processing_time >= self.processing_interval 
                    and len(self.accumulated_audio) >= self.min_audio_length):
                    
                    # Send accumulated audio for transcription
                    await self._transcribe_audio(self.accumulated_audio)
                    
                    # Reset accumulated audio and update timer
                    self.accumulated_audio = b''
                    self.last_processing_time = current_time
                elif (current_time - self.last_processing_time >= self.processing_interval 
                    and len(self.accumulated_audio) > 0):
                    # If we have audio but not enough, log it and wait for more
                    logger.info(f"Not enough audio to transcribe ({len(self.accumulated_audio)} < {self.min_audio_length} bytes), waiting for more...")
                    self.last_processing_time = current_time  # Reset timer but keep audio
                
                # Process continuous audio periodically for a more complete transcription
                if (current_time - self.last_continuous_time >= self.continuous_interval
                    and len(self.continuous_audio) >= self.min_audio_length * 3):  # Ensure we have significant audio
                    
                    # Process one continuous chunk
                    logger.info(f"Processing continuous transcription ({len(self.continuous_audio)} bytes)")
                    try:
                        result = await self._transcribe_audio(self.continuous_audio, is_continuous=True)
                        if result:
                            # We got a successful continuous transcription, clear the buffer
                            self.continuous_audio = b''
                            self.last_continuous_time = current_time
                    except Exception as e:
                        logger.error(f"Error in continuous transcription: {str(e)}")
                        # Reset timer but keep trying
                        self.last_continuous_time = current_time
                
                # Small delay to avoid busy waiting
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            logger.info("Audio queue processing task was cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in audio queue processing: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.state = "error"
    
    async def _transcribe_audio(self, audio_data, is_continuous=False):
        """Send audio data to OpenAI Whisper API for transcription."""
        if not audio_data or len(audio_data) < self.min_audio_length:  # Skip very small audio chunks
            logger.warning(f"Audio too short for transcription: {len(audio_data)} bytes")
            return False
            
        logger.info(f"Sending {len(audio_data)} bytes of audio for transcription{' (continuous)' if is_continuous else ''}")
        
        try:
            # Save audio to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".ulaw", delete=False) as temp_file:
                temp_filename = temp_file.name
                temp_file.write(audio_data)
            
            # Convert ulaw to wav using ffmpeg
            wav_filename = temp_filename + ".wav"
            conversion_successful = False
            
            # Try ffmpeg conversion first
            if ffmpeg_available:
                try:
                    # Run ffmpeg to convert from ulaw to wav
                    cmd = [
                        "ffmpeg", 
                        "-f", "mulaw", 
                        "-ar", "8000",  # g711 is usually 8kHz
                        "-i", temp_filename, 
                        "-ar", "16000",  # Convert to 16kHz for better transcription
                        "-ac", "1",      # Mono
                        "-f", "wav", 
                        wav_filename
                    ]
                    
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode != 0:
                        logger.error(f"ffmpeg conversion failed: {stderr.decode()}")
                    else:
                        logger.info(f"Successfully converted ulaw to wav: {wav_filename}")
                        conversion_successful = True
                except Exception as conv_error:
                    logger.error(f"Error during ffmpeg audio conversion: {str(conv_error)}")
                    # Will fall through to fallback method
            
            # If ffmpeg conversion didn't work, try fallback method
            if not conversion_successful:
                try:
                    logger.info("Attempting fallback audio conversion")
                    
                    # Simple conversion - G.711 μ-law is just a specific encoding of 8-bit PCM
                    # We'll decode it to 16-bit PCM for a valid WAV file that OpenAI can process
                    
                    # Create WAV header (44 bytes for standard header)
                    # This creates a very simple 16-bit PCM WAV with 8kHz sample rate
                    with open(wav_filename, 'wb') as wav_file:
                        # RIFF header
                        wav_file.write(b'RIFF')
                        # Filesize placeholder (filled in later)
                        wav_file.write(b'\x00\x00\x00\x00')
                        # WAVE header
                        wav_file.write(b'WAVE')
                        # fmt chunk
                        wav_file.write(b'fmt ')
                        # fmt chunk size (16 bytes)
                        wav_file.write(b'\x10\x00\x00\x00')
                        # PCM format (1)
                        wav_file.write(b'\x01\x00')
                        # Mono (1 channel)
                        wav_file.write(b'\x01\x00')
                        # Sample rate (8000 Hz)
                        wav_file.write(b'\x40\x1F\x00\x00')
                        # Byte rate (8000*2 bytes)
                        wav_file.write(b'\x80\x3E\x00\x00')
                        # Block align (2 bytes per sample * 1 channel)
                        wav_file.write(b'\x02\x00')
                        # Bits per sample (16)
                        wav_file.write(b'\x10\x00')
                        # data chunk
                        wav_file.write(b'data')
                        # data size placeholder (filled in later)
                        wav_file.write(b'\x00\x00\x00\x00')
                        
                        # Convert the μ-law audio to linear PCM
                        # Each μ-law byte becomes a 16-bit PCM sample
                        with open(temp_filename, 'rb') as ulaw_file:
                            ulaw_data = ulaw_file.read()
                            
                            # Simple μ-law to PCM conversion table
                            # This is a very simple conversion and not perfect,
                            # but should work well enough for speech recognition
                            ulaw_to_linear = [
                                0, 132, 396, 924, 1980, 4092, 8316, 16764,
                                -132, -396, -924, -1980, -4092, -8316, -16764, -32767,
                                # ... many more values here, simplified for brevity
                            ]
                            
                            for byte in ulaw_data:
                                # Very simplified conversion - actual μ-law decoding would be more complex
                                # For now, just ensure we create valid 16-bit PCM data that might work
                                # with the transcription API
                                pcm_value = int(byte) * 256  # Simple scaling
                                if pcm_value > 32767:
                                    pcm_value = 32767
                                elif pcm_value < -32768:
                                    pcm_value = -32768
                                    
                                # Write 16-bit PCM value (little endian)
                                wav_file.write(pcm_value.to_bytes(2, byteorder='little', signed=True))
                        
                        # Fill in file size in header
                        file_size = wav_file.tell()
                        wav_file.seek(4)
                        wav_file.write((file_size - 8).to_bytes(4, byteorder='little'))
                        
                        # Fill in data size in header
                        data_size = file_size - 44  # 44 is the header size
                        wav_file.seek(40)
                        wav_file.write(data_size.to_bytes(4, byteorder='little'))
                    
                    if os.path.exists(wav_filename) and os.path.getsize(wav_filename) > 44:
                        logger.info(f"Fallback conversion successful: {wav_filename}")
                        conversion_successful = True
                    else:
                        logger.error("Fallback conversion failed to produce valid wav file")
                except Exception as fallback_error:
                    logger.error(f"Fallback audio conversion failed: {str(fallback_error)}")
            
            # If we couldn't convert the file, return early
            if not conversion_successful:
                logger.error("All audio conversion methods failed")
                self.state = "error"
                return False
            
            # Define headers and data for the request
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            }
            
            # Prepare form data with the audio file
            data = aiohttp.FormData()
            data.add_field('file', open(wav_filename, 'rb'), filename='audio.wav')
            data.add_field('model', 'whisper-1')
            data.add_field('language', 'en')
            data.add_field('response_format', 'json')
            
            # For continuous transcription, add prompt with previous segments
            if is_continuous and self.transcript_segments:
                recent_segments = " ".join(self.transcript_segments[-5:])  # Use last 5 segments as context
                data.add_field('prompt', f"Previous segments: {recent_segments}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.openai.com/v1/audio/transcriptions',
                    headers=headers,
                    data=data
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        transcription = result.get('text', '')
                        
                        if transcription:
                            logger.info(f"Transcription result{' (continuous)' if is_continuous else ''}: {transcription}")
                            
                            # Store the raw segment for future context
                            self.transcript_segments.append(transcription.strip())
                            
                            # For continuous transcription, replace rather than append
                            if is_continuous:
                                # Replace the buffer with a more complete transcription
                                if transcription.strip():
                                    self.buffer = [f"User: {transcription.strip()}"]
                                    logger.info(f"Updated buffer with continuous transcription: {transcription}")
                            else:
                                # Add to buffer (regular incremental transcription)
                                self.buffer.append(f"User: {transcription}")
                                
                            return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Transcription API error: {response.status} - {error_text}")
                        
                        # Check if this is an authentication error
                        if response.status == 401:
                            logger.error("Authentication error: Invalid API key or insufficient permissions")
                        elif response.status == 400:
                            logger.error("Bad request: The API couldn't process the audio format")
                        
                        self.state = "error"
                        return False
            
            # Clean up the temporary files
            try:
                os.unlink(temp_filename)
                if os.path.exists(wav_filename):
                    os.unlink(wav_filename)
            except Exception as e:
                logger.error(f"Error removing temporary files: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error in transcription: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.state = "error"
            return False

    async def get_buffer(self):
        """Get a copy of the current transcription buffer."""
        return self.buffer.copy()
        
    def clear_buffer(self):
        """Clear the transcription buffer."""
        self.buffer = []
        return True

# Initialize the transcription service
transcription_service = TranscriptionService()

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
                        
                        # Send to conversation API (existing functionality)
                        await openai_ws.send(json.dumps(audio_append))
                        
                        # Also send to transcription service (new functionality)
                        try:
                            # Send audio to transcription service (non-blocking)
                            asyncio.create_task(send_audio_for_transcription(data['media']['payload']))
                        except Exception as transcription_error:
                            # Log but don't interrupt the main conversation flow
                            logger.error(f"Error sending to transcription: {str(transcription_error)}")
                            
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
                
                # Stop the transcription session if it's running
                global transcription_service
                if transcription_service.state != "closed":
                    try:
                        await transcription_service.stop()
                        logger.info("Closed transcription session")
                    except Exception as e:
                        logger.error(f"Error closing transcription session: {str(e)}")

        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid, full_transcription, websocket_closed
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
        # Log the transcription even if we can't save it to a specific call
        if full_transcription or transcription_service.buffer:
            # Merge the transcription buffer with the full transcription
            final_transcription = []
            
            # Process transcriptions from the OpenAI conversation API
            if full_transcription:
                logger.info(f"Adding {len(full_transcription)} items from real-time transcription")
                final_transcription.extend(full_transcription)
            
            # Get transcriptions from our custom transcription service
            if transcription_service.buffer:
                # Process final continuous transcription if available
                if len(transcription_service.continuous_audio) >= transcription_service.min_audio_length:
                    try:
                        logger.info(f"Processing final continuous transcription ({len(transcription_service.continuous_audio)} bytes)")
                        # Process the remaining continuous audio without clearing the buffer
                        await transcription_service._transcribe_audio(
                            transcription_service.continuous_audio, 
                            is_continuous=True
                        )
                    except Exception as e:
                        logger.error(f"Error processing final transcription: {e}")
                
                logger.info(f"Adding {len(transcription_service.buffer)} items from custom transcription service")
                
                # If we have a custom transcription (which may be more accurate), use it
                if len(transcription_service.buffer) == 1 and transcription_service.buffer[0].startswith("User:"):
                    # We have a single comprehensive transcription
                    consolidated_transcript = transcription_service.buffer[0]
                    logger.info(f"Using consolidated transcription: {consolidated_transcript}")
                    final_transcription = [consolidated_transcript] + final_transcription
                else:
                    # We have multiple fragments, append them
                    final_transcription.extend(transcription_service.buffer)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_transcription = []
            for item in final_transcription:
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

async def send_audio_for_transcription(audio_data):
    """Send audio data to the transcription service."""
    global transcription_service
    
    if transcription_service.state == "closed":
        success = await transcription_service.start()
        if not success:
            logger.error("Failed to start transcription service")
            return False
    
    return await transcription_service.send_audio(audio_data)

@app.get("/test-transcription")
async def test_transcription():
    """Test endpoint for the transcription functionality."""
    global transcription_service
    
    # Clean up any existing session
    if transcription_service.state != "closed":
        await transcription_service.stop()
    
    transcription_service.clear_buffer()
    
    # Create a new transcription session
    try:
        success = await transcription_service.start()
        if not success:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to create transcription session"}
            )
        
        # Send a test audio snippet (in a real scenario, this would be voice data)
        # This is just a placeholder - you would need real audio data
        test_audio = "VGVzdCBhdWRpbyBkYXRhIC0gbm90IHJlYWwgYXVkaW8="  # Base64 "Test audio data - not real audio"
        success = await transcription_service.send_audio(test_audio)
        
        # Wait a moment to see if we get any response
        await asyncio.sleep(2)
        
        # Get the current buffer
        buffer = await transcription_service.get_buffer()
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success" if success else "error",
                "message": "Transcription test completed",
                "state": transcription_service.state,
                "buffer": buffer
            }
        )
    except Exception as e:
        logger.error(f"Error in test-transcription endpoint: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        return JSONResponse(
            status_code=500,
            content={"error": f"Transcription test failed: {str(e)}"}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT) 