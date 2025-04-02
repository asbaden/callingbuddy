# Calling Buddy

A voice assistant application that uses Twilio and OpenAI's Realtime API to create a conversational AI experience over phone calls.

## Project Structure

This repository contains two main components:
1. **Backend Server** - A Python FastAPI server that handles the communication between Twilio and OpenAI
2. **Mobile App** - A React Native/Expo app that provides a user interface to interact with the service

## Call Flow Options

This application supports two ways of connecting users with the AI assistant:

1. **Inbound Calls** - Users can call the Twilio phone number directly to speak with the AI assistant.
2. **Outbound Calls** - Users can enter their phone number in the mobile app, and the service will call them.

## Prerequisites

- Python 3.9+
- A Twilio account with a phone number capable of Voice
- An OpenAI account with Realtime API access
- Node.js 14+ (for the mobile app)
- (Optional) ngrok or another tunneling solution to expose your local server to the internet for testing

## Backend Setup

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/callingbuddy.git
   cd callingbuddy
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up your environment variables in the `.env` file:
   ```
   OPENAI_API_KEY=your_openai_api_key
   TWILIO_ACCOUNT_SID=your_twilio_account_sid
   TWILIO_AUTH_TOKEN=your_twilio_auth_token
   TWILIO_PHONE_NUMBER=your_twilio_phone_number
   ```

## Running the Backend Server

To start the server locally:

```
python main.py
```

The server will start on port 5050 by default. You can change this by setting the `PORT` environment variable in your `.env` file.

### Using with Twilio

To connect this application to Twilio, you need to:

1. Make your server publicly accessible (using ngrok or a similar service):
   ```
   ngrok http 5050
   ```

2. In your Twilio console, configure the Voice URL for your phone number to point to your server's `/incoming-call` endpoint:
   ```
   https://your-ngrok-subdomain.ngrok.io/incoming-call
   ```

## Mobile App

The mobile app allows users to either call the Twilio number directly or request that the AI assistant call them.

### Running the Mobile App

```
cd CallingBuddyApp
npm install
npx expo start
```

### Customizing the App

You can customize the app by modifying:
- The Twilio phone number in `CallingBuddyApp/utils/config.ts`
- The UI in the screens components
- The app information in `CallingBuddyApp/app.json`

## Deployment

### Backend Deployment to Render

This application is ready to be deployed to Render:

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Configure the service:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add your environment variables in the Render dashboard:
   - OPENAI_API_KEY
   - TWILIO_ACCOUNT_SID
   - TWILIO_AUTH_TOKEN
   - TWILIO_PHONE_NUMBER

### Mobile App Deployment

To build the mobile app for production:

```bash
cd CallingBuddyApp
# Install EAS CLI
npm install -g eas-cli
# Configure EAS
eas configure
# Build for Android or iOS
eas build --platform android
eas build --platform ios
```

## License

MIT 