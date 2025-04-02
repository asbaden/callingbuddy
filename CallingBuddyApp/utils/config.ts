// Config file for Calling Buddy App

// Backend API URL
export const BACKEND_URL = 'https://callingbuddy.onrender.com';

// Network settings
export const NETWORK_CONFIG = {
  timeout: 60000,        // 60 second timeout
  maxRetries: 3,         // Number of retries for failed requests
  retryDelay: 1000,      // Delay between retries in ms
};

// Twilio phone number to call
export const TWILIO_PHONE_NUMBER = '+18446128030';

// App version
export const APP_VERSION = '1.0.0'; 