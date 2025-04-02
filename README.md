# Calling Buddy

A voice assistant application that uses Twilio and OpenAI's Realtime API to create a conversational AI experience over phone calls.

## Prerequisites

- Python 3.9+
- A Twilio account with a phone number capable of Voice
- An OpenAI account with Realtime API access
- (Optional) ngrok or another tunneling solution to expose your local server to the internet for testing

## Setup

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

## Running the Application

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

## Usage

Once the server is running and connected to Twilio:

1. Call your Twilio phone number
2. You'll hear a welcome message
3. Start talking with the AI assistant

## Deployment to Render

This application is ready to be deployed to Render:

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Configure the service:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add your environment variables in the Render dashboard

## License

MIT 