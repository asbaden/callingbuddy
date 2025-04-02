-- CallingBuddy Database Schema
-- This file defines all tables required for the application

-- Users table to store basic user information
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_number TEXT NOT NULL UNIQUE,
    name TEXT,
    recovery_program TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Call schedules for recurring check-ins
CREATE TABLE IF NOT EXISTS call_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    days_of_week INTEGER[], -- Array of days (0=Sunday, 1=Monday, etc.)
    time_of_day TIME NOT NULL, -- Time in user's local timezone
    timezone TEXT DEFAULT 'UTC',
    active BOOLEAN DEFAULT TRUE,
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

-- Table for storing structured responses to 10th step inventory questions
CREATE TABLE IF NOT EXISTS inventory_responses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    response TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add RLS (Row Level Security) policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_responses ENABLE ROW LEVEL SECURITY;

-- Create policies that allow users to only see their own data
CREATE POLICY "Users can view their own data" 
    ON users FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update their own data" 
    ON users FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Users can view their own schedules" 
    ON call_schedules FOR SELECT USING (
        user_id IN (SELECT id FROM users WHERE id = auth.uid())
    );

CREATE POLICY "Users can manage their own schedules" 
    ON call_schedules FOR ALL USING (
        user_id IN (SELECT id FROM users WHERE id = auth.uid())
    );

CREATE POLICY "Users can view their own calls" 
    ON calls FOR SELECT USING (
        user_id IN (SELECT id FROM users WHERE id = auth.uid())
    );

CREATE POLICY "Users can view their own transcriptions" 
    ON transcriptions FOR SELECT USING (
        call_id IN (SELECT id FROM calls WHERE user_id IN 
            (SELECT id FROM users WHERE id = auth.uid())
        )
    );

CREATE POLICY "Users can view their own inventory responses" 
    ON inventory_responses FOR SELECT USING (
        call_id IN (SELECT id FROM calls WHERE user_id IN 
            (SELECT id FROM users WHERE id = auth.uid())
        )
    );

-- Create service role policies for backend operations
CREATE POLICY "Service can manage all user data" 
    ON users USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage all call schedules" 
    ON call_schedules USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage all calls" 
    ON calls USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage all transcriptions" 
    ON transcriptions USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage all inventory responses" 
    ON inventory_responses USING (auth.role() = 'service_role');

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

CREATE TRIGGER update_call_schedules_updated_at
BEFORE UPDATE ON call_schedules
FOR EACH ROW EXECUTE FUNCTION update_updated_at(); 