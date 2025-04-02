# CallingBuddy Database Setup

This directory contains database schema and helper functions for the Supabase backend.

## Setting Up the Database

1. Log in to your Supabase dashboard: https://app.supabase.com/
2. Select your project
3. Navigate to the SQL Editor
4. Paste the contents of `schema.sql` and run it

## Database Structure

The database includes the following tables:

- **users** - Stores user information and phone numbers
- **call_schedules** - Defines recurring call schedules for users
- **calls** - Records of actual calls placed through the system
- **transcriptions** - Stored transcripts of calls
- **inventory_responses** - Structured responses to recovery questions

## Environment Variables

Make sure your `.env` file includes:

```
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

## Usage

The `supabase_client.py` module provides helper functions to interact with the database:

```python
from database.supabase_client import create_user, create_call, create_transcription

# Create a user
user = await create_user("+15551234567", "John Doe")

# Create a call record
call = await create_call(user["id"], "TWILIO_CALL_SID")

# Store a transcription
transcription = await create_transcription(call["id"], "Call transcription content...")
```

## Security

The schema includes Row Level Security (RLS) policies to ensure:

1. Users can only access their own data
2. Service role (backend) can access all data
3. Public access is restricted

Remember to keep your service role key secure and never expose it in client-side code. 