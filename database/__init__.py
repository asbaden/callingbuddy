"""
Database module for CallingBuddy application.
Provides Supabase integration and helpers for database operations.
"""

from database.supabase_client import (
    create_user, 
    get_user_by_phone,
    create_call,
    update_call,
    get_call_by_sid,
    create_transcription,
    get_transcription_by_call_id,
    create_call_schedule,
    get_active_schedules,
    create_inventory_response,
    get_inventory_responses_by_call,
    supabase_available
)

__all__ = [
    'create_user',
    'get_user_by_phone',
    'create_call',
    'update_call',
    'get_call_by_sid',
    'create_transcription',
    'get_transcription_by_call_id',
    'create_call_schedule',
    'get_active_schedules',
    'create_inventory_response',
    'get_inventory_responses_by_call',
    'supabase_available'
] 