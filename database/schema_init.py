import os
import logging
from supabase import create_client
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Supabase client using admin credentials
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Schema initialization query
SCHEMA_SQL = """
-- Users table to store basic user information
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_number TEXT NOT NULL UNIQUE,
    name TEXT,
    recovery_program TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Record of actual calls made by the system
CREATE TABLE IF NOT EXISTS calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    call_sid TEXT, -- Twilio Call SID
    status TEXT, -- 'completed', 'failed', 'busy', etc.
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Transcriptions of calls
CREATE TABLE IF NOT EXISTS transcriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    content TEXT NOT NULL, -- The full transcription text
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create function to handle updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at fields
CREATE TRIGGER update_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_updated_at();
"""

def init_schema():
    """Initialize the database schema if tables don't exist."""
    try:
        # Create Supabase client
        logger.info(f"Connecting to Supabase at {supabase_url}")
        client = create_client(supabase_url, supabase_key)

        # Execute the schema SQL using a raw query
        logger.info("Initializing database schema...")
        
        # First check if tables already exist
        check_result = client.table("users").select("*").limit(1).execute()
        
        if len(check_result.data) > 0:
            logger.info("Tables already exist, skipping schema initialization")
            return True
            
        # Execute the schema SQL directly
        logger.info("Creating tables...")
        client.rpc("exec_sql", {"sql": SCHEMA_SQL}).execute()
        
        # Verify tables were created
        verify = client.table("users").select("*").limit(1).execute()
        
        logger.info("Schema initialization complete!")
        return True
    except Exception as e:
        logger.error(f"Error initializing schema: {str(e)}")
        return False

if __name__ == "__main__":
    init_schema() 