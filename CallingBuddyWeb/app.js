document.addEventListener('DOMContentLoaded', function() {
    // Backend URL
    const BACKEND_URL = 'https://callingbuddy.onrender.com';
    
    // Get DOM elements
    const phoneNumberInput = document.getElementById('phoneNumber');
    const callButton = document.getElementById('callButton');
    const buttonText = callButton.querySelector('.btn-text');
    const spinner = callButton.querySelector('.spinner');
    const resultDiv = document.getElementById('result');
    const logsDiv = document.getElementById('logs');
    const transcriptArea = document.getElementById('transcriptArea');
    const transcriptOutput = document.getElementById('transcriptOutput');
    
    // Initialize
    phoneNumberInput.focus();
    
    // Add event listener for the call button
    callButton.addEventListener('click', initiateCall);
    
    // Log function
    function log(message) {
        const now = new Date();
        const timestamp = now.toTimeString().substring(0, 8);
        
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        
        const formattedMessage = typeof message === 'object' 
            ? JSON.stringify(message, null, 2) 
            : message;
            
        logEntry.innerHTML = `<span class="timestamp">[${timestamp}]</span> ${formattedMessage}`;
        
        logsDiv.appendChild(logEntry);
        logsDiv.scrollTop = logsDiv.scrollHeight;
        
        // Also log to console
        console.log(`[${timestamp}] ${message}`);
    }
    
    // Show result
    function showResult(message, isSuccess = true) {
        resultDiv.textContent = message;
        resultDiv.className = `result ${isSuccess ? 'success' : 'error'}`;
        resultDiv.classList.remove('hidden');
    }
    
    let websocket = null; // Global variable to hold the WebSocket instance
    let mediaRecorder = null; // To hold the MediaRecorder instance
    let audioStream = null; // To hold the microphone audio stream

    // Initiate call
    async function initiateCall() {
        // Show loading state
        callButton.disabled = true;
        spinner.classList.remove('hidden');
        buttonText.textContent = 'Initiating...';
        resultDiv.classList.add('hidden');
        transcriptArea.classList.remove('hidden');
        transcriptOutput.innerHTML = '';
        
        // Get call type from the selection
        const callTypeElement = document.getElementById('callTypeSelect');
        const callType = callTypeElement ? callTypeElement.value : 'morning';

        log(`Initiating ${callType} virtual session...`);
        log(`Sending request to: ${BACKEND_URL}/call-user`);
        
        try {
            const response = await fetch(`${BACKEND_URL}/call-user`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    call_type: callType 
                })
            });
            
            log(`Received status: ${response.status}`);
            const data = await response.text();
            log(`Response: ${data}`);
            
            let jsonData;
            try {
                jsonData = JSON.parse(data);
                log(`Parsed JSON: ${JSON.stringify(jsonData)}`);
            } catch (e) {
                log(`Could not parse JSON response: ${data}`);
                jsonData = null;
            }
            
            if (response.ok && jsonData && jsonData.call_record_id) {
                // SUCCESS: Start WebSocket Session
                const callRecordId = jsonData.call_record_id;
                showResult(`Virtual session initiated (ID: ${callRecordId}). Connecting...`);
                log(`Call Record ID: ${callRecordId}`);
                
                startWebSocketSession(callRecordId);
                
                // Keep button disabled, update text
                buttonText.textContent = 'Session Active';

            } else {
                // ERROR
                const errorMessage = (jsonData && jsonData.error) 
                    ? jsonData.error 
                    : `Error: ${response.status} ${response.statusText}`;
                    
                showResult(errorMessage, false);
                log(`Error: ${errorMessage}`);
                // Reset button state on error
                callButton.disabled = false;
                spinner.classList.add('hidden');
                buttonText.textContent = 'Start AI Session';
            }
        } catch (error) {
            // Network error
            log(`Fetch error: ${error.message}`);
            showResult(`Network error: ${error.message}. Please try again later.`, false);
            // Reset button state on error
            callButton.disabled = false;
            spinner.classList.add('hidden');
            buttonText.textContent = 'Start AI Session';
        } 
    }
    
    // --- WebSocket Handling --- 
    function startWebSocketSession(callRecordId) {
        // Replace BACKEND_URL with WEBSOCKET_URL derivation
        let wsBackendUrl = BACKEND_URL.replace(/^http/, 'ws');
        const wsUrl = `${wsBackendUrl}/media-stream?call_record_id=${callRecordId}`;
        log(`Connecting WebSocket to: ${wsUrl}`);
        
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            log('WebSocket already open. Closing previous connection.');
            websocket.close();
        }
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            log('Stopped previous media recorder.');
        }
        if (audioStream) {
            audioStream.getTracks().forEach(track => track.stop());
            log('Stopped previous audio stream tracks.');
        }

        websocket = new WebSocket(wsUrl);

        websocket.onopen = async (event) => { // Make onopen async
            log('WebSocket connection established.');
            showResult('Connected to AI. Session active.');
            
            // --- START MICROPHONE CAPTURE --- 
            try {
                log('Requesting microphone access...');
                audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                log('Microphone access granted.');
                
                // TODO: Initialize MediaRecorder and start sending audio
                
            } catch (err) {
                log(`Error getting microphone access: ${err.name} - ${err.message}`);
                showResult(`Microphone access denied or unavailable: ${err.message}`, false);
                // Close WebSocket if mic access fails?
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    websocket.close(1008, "Microphone access failed");
                }
            }
            // --- END MICROPHONE CAPTURE --- 
        };

        websocket.onmessage = (event) => {
            log('Received message via WebSocket:');
            try {
                const message = JSON.parse(event.data);
                log(JSON.stringify(message, null, 2)); // Pretty print message
                
                if (message.event === 'audio') {
                    // TODO: Handle incoming audio playback
                    log('Received AI audio chunk.');
                } else if (message.event === 'transcript') {
                    // TODO: Handle incoming transcript display
                    log(`Transcript (${message.sender}): ${message.text}`);
                } else {
                    log(`Unknown message event type: ${message.event}`);
                }
            } catch (e) {
                log(`Error parsing WebSocket message: ${e}`);
                log(`Raw message data: ${event.data}`);
            }
        };

        websocket.onerror = (event) => {
            log(`WebSocket Error: ${JSON.stringify(event)}`);
            showResult('WebSocket connection error.', false);
            // Clean up audio stream on error too
            if (audioStream) {
                audioStream.getTracks().forEach(track => track.stop());
                audioStream = null;
            }
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
                mediaRecorder = null;
            }
            // Reset button state on error
            callButton.disabled = false;
            spinner.classList.add('hidden');
            buttonText.textContent = 'Start AI Session';
        };

        websocket.onclose = (event) => {
            log(`WebSocket connection closed. Code: ${event.code}, Reason: ${event.reason}`);
            showResult(`Session ended (Code: ${event.code})`, event.code !== 1000 && event.code !== 1005);
            websocket = null; // Clear the global variable
            
            // --- STOP MICROPHONE CAPTURE --- 
            log('Stopping microphone capture due to WebSocket close.');
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
                mediaRecorder = null;
            }
            if (audioStream) {
                audioStream.getTracks().forEach(track => track.stop());
                audioStream = null;
            }
            // --- END STOP MICROPHONE --- 
            
            // Reset button state on close
            callButton.disabled = false;
            spinner.classList.add('hidden');
            buttonText.textContent = 'Start AI Session';
        };
    }
    
    // Initial log
    log('Calling Buddy Web initialized. Ready to make calls.');
}); 