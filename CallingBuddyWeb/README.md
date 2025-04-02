# CallingBuddy Web

A web interface for the CallingBuddy AI voice assistant that allows users to request a call from an AI assistant powered by OpenAI's Realtime API and Twilio.

## Features

- Simple form to input phone number
- Calls user's phone via Twilio
- Connects user to OpenAI Realtime API for voice conversation
- Real-time feedback on call status
- Detailed request logging for debugging
- Responsive design works on mobile and desktop

## Getting Started

### Prerequisites

- Node.js (v12 or higher)
- npm or yarn

### Installation

1. Clone the repository or download the files
2. Install dependencies:
   ```
   cd CallingBuddyWeb
   npm install
   ```

### Running the App

Start the local server:

```
npm start
```

This will launch the app at http://localhost:3000

### Accessing from Other Devices

To test on mobile devices on your local network:

1. Find your computer's IP address:
   - macOS/Linux: `ifconfig` or `ip addr`
   - Windows: `ipconfig`

2. Access the app from another device using:
   ```
   http://YOUR_IP_ADDRESS:3000
   ```

## Deployment

### Deploying to Render

1. Push this directory to a GitHub repository
2. Create a new Web Service on Render
3. Select your repository and set:
   - Build Command: `npm install`
   - Start Command: `node server.js`

## Configuration

Edit the BACKEND_URL in app.js to point to your deployed backend service.

## License

MIT 