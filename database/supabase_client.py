import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Debug output to verify API keys are loaded correctly
print(f"Supabase URL: {supabase_url}")
print(f"Supabase Key: {supabase_key[:10]}...") # Print only first 10 chars for security

# Validate that we have valid credentials before creating client
if not supabase_url or not supabase_url.startswith("https://"):
    raise ValueError("Invalid SUPABASE_URL - must start with https://")
    
if not supabase_key:
    raise ValueError("Missing SUPABASE_SERVICE_ROLE_KEY in environment variables")

try:
    # Simple initialization for version 1.0.3
    supabase = create_client(supabase_url, supabase_key)
except Exception as e:
    print(f"Error initializing Supabase client: {e}")
    raise

# User operations
async def create_user(phone_number, name=None, recovery_program=None):
    """Create a new user in the database."""
    user_data = {
        "phone_number": phone_number,
        "name": name,
        "recovery_program": recovery_program
    }
    
    result = supabase.table("users").insert(user_data).execute()
    return result.data[0] if result.data else None

async def get_user_by_phone(phone_number):
    """Get a user by their phone number."""
    result = supabase.table("users").select("*").eq("phone_number", phone_number).execute()
    return result.data[0] if result.data else None

# Call operations
async def create_call(user_id, call_sid=None, status="initiated"):
    """Create a new call record."""
    call_data = {
        "user_id": user_id,
        "call_sid": call_sid,
        "status": status
    }
    
    result = supabase.table("calls").insert(call_data).execute()
    return result.data[0] if result.data else None

async def update_call(call_id, status=None, ended_at=None, duration_seconds=None):
    """Update an existing call record."""
    call_data = {}
    if status:
        call_data["status"] = status
    if ended_at:
        call_data["ended_at"] = ended_at
    if duration_seconds:
        call_data["duration_seconds"] = duration_seconds
    
    result = supabase.table("calls").update(call_data).eq("id", call_id).execute()
    return result.data[0] if result.data else None

async def get_call_by_sid(call_sid):
    """Get a call by Twilio call SID."""
    result = supabase.table("calls").select("*").eq("call_sid", call_sid).execute()
    return result.data[0] if result.data else None

# Transcription operations
async def create_transcription(call_id, content):
    """Store a call transcription."""
    transcription_data = {
        "call_id": call_id,
        "content": content
    }
    
    result = supabase.table("transcriptions").insert(transcription_data).execute()
    return result.data[0] if result.data else None

async def get_transcription_by_call_id(call_id):
    """Get a transcription by call ID."""
    result = supabase.table("transcriptions").select("*").eq("call_id", call_id).execute()
    return result.data[0] if result.data else None

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