# Calling Buddy Mobile App

This is the mobile companion app for the Calling Buddy AI voice assistant. It provides an easy way to connect with our AI assistant through phone calls.

## Features

- One-touch calling to the AI assistant
- Information about how the service works
- Cross-platform (iOS and Android)

## Prerequisites

- Node.js 14+
- Expo CLI
- iOS/Android device or simulator

## Getting Started

1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the Expo development server:
   ```bash
   npx expo start
   ```

3. Run on a device or simulator:
   - Press `i` to run on iOS simulator
   - Press `a` to run on Android simulator
   - Scan QR code with Expo Go app on your physical device

## Configuration

You can modify the backend URL and Twilio phone number in `utils/config.ts` if needed.

## Building for Production

To create a production build:

```bash
# For Android
eas build --platform android

# For iOS
eas build --platform ios
```

## Backend Service

This app works in conjunction with the Calling Buddy backend service, which handles the communication between Twilio and OpenAI's Realtime API. The backend is hosted on Render.com.

## License

MIT 