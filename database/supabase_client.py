import os
import logging
import traceback
from supabase import create_client, Client
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Debug output to verify API keys are loaded correctly
logger.info(f"Supabase URL: {supabase_url}")
if supabase_key:
    logger.info(f"Supabase Key length: {len(supabase_key)} chars")
    logger.info(f"Supabase Key first 10 chars: {supabase_key[:10]}...")
    logger.info(f"Supabase Key last 10 chars: {supabase_key[-10:]}")
else:
    logger.error("Supabase key is not set!")

# Flag to track if Supabase is available
supabase_available = False
supabase = None

# Try to initialize Supabase client
try:
    # Simple initialization for version 1.0.3
    if supabase_url and supabase_key:
        logger.info("Attempting to initialize Supabase client...")
        supabase = create_client(supabase_url, supabase_key)
        
        # Test the connection with a simple query
        logger.info("Testing Supabase connection with a simple query...")
        test = supabase.table("users").select("*").limit(1).execute()
        logger.info(f"Supabase test query result: {test}")
        
        supabase_available = True
        logger.info("Supabase client initialized successfully!")
    else:
        missing_vars = []
        if not supabase_url:
            missing_vars.append("SUPABASE_URL")
        if not supabase_key:
            missing_vars.append("SUPABASE_SERVICE_ROLE_KEY")
        logger.error(f"Missing Supabase credentials: {', '.join(missing_vars)}. Database functionality will be disabled.")
except Exception as e:
    logger.error(f"Error initializing Supabase client: {str(e)}")
    logger.error(f"Error details: {traceback.format_exc()}")
    logger.warning("Running without database functionality - calls will not be stored!")

# User operations
async def create_user(phone_number, name=None, recovery_program=None):
    """Create a new user in the database."""
    if not supabase_available:
        logger.warning("Supabase not available - user creation skipped")
        return {"id": "dummy-user-id", "phone_number": phone_number}
    
    try:
        user_data = {
            "phone_number": phone_number,
            "name": name,
            "recovery_program": recovery_program
        }
        
        result = supabase.table("users").insert(user_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return {"id": "dummy-user-id", "phone_number": phone_number}

async def get_user_by_phone(phone_number):
    """Get a user by their phone number."""
    if not supabase_available:
        logger.warning("Supabase not available - get user skipped")
        return {"id": "dummy-user-id", "phone_number": phone_number}
    
    try:
        result = supabase.table("users").select("*").eq("phone_number", phone_number).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        return {"id": "dummy-user-id", "phone_number": phone_number}

# Call operations
async def create_call(user_id, call_sid=None, status="initiated"):
    """Create a new call record."""
    if not supabase_available:
        logger.warning("Supabase not available - call creation skipped")
        return {"id": "dummy-call-id", "user_id": user_id, "call_sid": call_sid}
    
    try:
        call_data = {
            "user_id": user_id,
            "call_sid": call_sid,
            "status": status
        }
        
        result = supabase.table("calls").insert(call_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error creating call: {e}")
        return {"id": "dummy-call-id", "user_id": user_id, "call_sid": call_sid}

async def update_call(call_id, status=None, ended_at=None, duration_seconds=None):
    """Update an existing call record."""
    if not supabase_available:
        logger.warning("Supabase not available - call update skipped")
        return {"id": call_id}
    
    try:
        call_data = {}
        if status:
            call_data["status"] = status
        if ended_at:
            call_data["ended_at"] = ended_at
        if duration_seconds:
            call_data["duration_seconds"] = duration_seconds
        
        result = supabase.table("calls").update(call_data).eq("id", call_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error updating call: {e}")
        return {"id": call_id}

async def get_call_by_sid(call_sid):
    """Get a call by Twilio call SID."""
    if not supabase_available:
        logger.warning("Supabase not available - get call skipped")
        return {"id": "dummy-call-id", "call_sid": call_sid}
    
    try:
        result = supabase.table("calls").select("*").eq("call_sid", call_sid).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error getting call: {e}")
        return {"id": "dummy-call-id", "call_sid": call_sid}

# Transcription operations
async def create_transcription(call_id, content):
    """Store a call transcription."""
    if not supabase_available:
        logger.warning("Supabase not available - transcription creation skipped")
        logger.info(f"Transcription would have been stored: {content[:100]}...")
        return {"id": "dummy-transcription-id", "call_id": call_id}
    
    try:
        transcription_data = {
            "call_id": call_id,
            "content": content
        }
        
        result = supabase.table("transcriptions").insert(transcription_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error creating transcription: {e}")
        return {"id": "dummy-transcription-id", "call_id": call_id}

async def get_transcription_by_call_id(call_id):
    """Get a transcription by call ID."""
    if not supabase_available:
        logger.warning("Supabase not available - get transcription skipped")
        return {"id": "dummy-transcription-id", "call_id": call_id, "content": "Transcription not available"}
    
    try:
        result = supabase.table("transcriptions").select("*").eq("call_id", call_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error getting transcription: {e}")
        return {"id": "dummy-transcription-id", "call_id": call_id, "content": "Error retrieving transcription"}

# Schedule operations
async def create_call_schedule(user_id, days_of_week, time_of_day, timezone="UTC", active=True):
    """Create a new call schedule."""
    schedule_data = {
        "user_id": user_id,
        "days_of_week": days_of_week,  # e.g., [0, 2, 4] for Sun, Tue, Thu
        "time_of_day": time_of_day,    # e.g., "08:00:00"
        "timezone": timezone,
        "active": active
    }
    
    result = supabase.table("call_schedules").insert(schedule_data).execute()
    return result.data[0] if result.data else None

async def get_active_schedules():
    """Get all active call schedules."""
    result = supabase.table("call_schedules").select("*").eq("active", True).execute()
    return result.data if result.data else []

# Inventory response operations
async def create_inventory_response(call_id, question_number, question_text, response):
    """Store an inventory question response."""
    response_data = {
        "call_id": call_id,
        "question_number": question_number,
        "question_text": question_text,
        "response": response
    }
    
    result = supabase.table("inventory_responses").insert(response_data).execute()
    return result.data[0] if result.data else None

async def get_inventory_responses_by_call(call_id):
    """Get all inventory responses for a specific call."""
    result = supabase.table("inventory_responses").select("*").eq("call_id", call_id).execute()
    return result.data if result.data else []

__all__ = [
    'create_user', 
    'get_user_by_phone',
    'create_call',
    'update_call',
    'get_call_by_sid',
    'create_transcription',
    'get_transcription_by_call_id',
    'supabase_available'
] 