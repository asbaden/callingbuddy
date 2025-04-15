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
    
    // Format phone number
    function formatPhoneNumber(phoneNumber) {
        // If number doesn't start with +, add +1 (for US)
        if (!phoneNumber.startsWith('+')) {
            return `+1${phoneNumber.replace(/\D/g, '')}`;
        }
        
        // Otherwise just remove non-digits except for the +
        return `+${phoneNumber.substring(1).replace(/\D/g, '')}`;
    }
    
    // Show result
    function showResult(message, isSuccess = true) {
        resultDiv.textContent = message;
        resultDiv.className = `result ${isSuccess ? 'success' : 'error'}`;
        resultDiv.classList.remove('hidden');
    }
    
    let websocket = null; // Global variable to hold the WebSocket instance

    // Initiate call
    async function initiateCall() {
        // Get and validate phone number
        const phoneNumber = phoneNumberInput.value.trim();
        
        if (!phoneNumber || phoneNumber.length < 10) {
            showResult('Please enter a valid phone number with country code', false);
            phoneNumberInput.focus();
            return;
        }
        
        // Format phone number
        const formattedNumber = formatPhoneNumber(phoneNumber);
        
        // Show loading state
        callButton.disabled = true;
        spinner.classList.remove('hidden');
        buttonText.textContent = 'Processing...';
        resultDiv.classList.add('hidden');
        
        // Get call type from the selection (assuming dropdown/radio with id="callTypeSelect")
        const callTypeElement = document.getElementById('callTypeSelect');
        const callType = callTypeElement ? callTypeElement.value : 'morning'; // Default to morning if not found

        log(`Initiating ${callType} call to: ${formattedNumber}`);
        log(`Sending request to: ${BACKEND_URL}/call-user`);
        
        try {
            const response = await fetch(`${BACKEND_URL}/call-user`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    phone_number: formattedNumber, 
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
                // --- SUCCESS: Start WebSocket Session --- 
                const callRecordId = jsonData.call_record_id;
                showResult(`Virtual session initiated (ID: ${callRecordId}). Connecting...`);
                log(`Call Record ID: ${callRecordId}`);
                phoneNumberInput.value = ''; // Clear input
                
                // Start the WebSocket connection
                startWebSocketSession(callRecordId);
                
                // Keep button disabled until WebSocket closes or call ends
                // We will re-enable it in the WebSocket close handler later
                buttonText.textContent = 'Connected'; 
                // Don't re-enable callButton here

            } else {
                // --- ERROR --- 
                const errorMessage = (jsonData && jsonData.error) 
                    ? jsonData.error 
                    : `Error: ${response.status} ${response.statusText}`;
                    
                showResult(errorMessage, false);
                log(`Error: ${errorMessage}`);
                // Reset button state on error
                callButton.disabled = false;
                spinner.classList.add('hidden');
                buttonText.textContent = 'Get AI Call';
            }
        } catch (error) {
            // Network error
            log(`Fetch error: ${error.message}`);
            showResult(`Network error: ${error.message}. Please try again later.`, false);
            // Reset button state on error
            callButton.disabled = false;
            spinner.classList.add('hidden');
            buttonText.textContent = 'Get AI Call';
        } 
        // Remove finally block resetting button - handled in success/error/close cases
    }
    
    // --- NEW FUNCTION: WebSocket Handling --- 
    function startWebSocketSession(callRecordId) {
        const wsUrl = `${BACKEND_URL}/media-stream?call_record_id=${callRecordId}`;
        log(`Connecting WebSocket to: ${wsUrl}`);
        
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            log('WebSocket already open. Closing previous connection.');
            websocket.close();
        }

        websocket = new WebSocket(wsUrl);

        websocket.onopen = (event) => {
            log('WebSocket connection established.');
            showResult('Connected to AI. Session active.');
            // TODO: Start microphone capture here
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
            // Reset button state on error
            callButton.disabled = false;
            spinner.classList.add('hidden');
            buttonText.textContent = 'Get AI Call';
        };

        websocket.onclose = (event) => {
            log(`WebSocket connection closed. Code: ${event.code}, Reason: ${event.reason}`);
            showResult(`Session ended (Code: ${event.code})`, !event.wasClean);
            websocket = null; // Clear the global variable
            // Reset button state on close
            callButton.disabled = false;
            spinner.classList.add('hidden');
            buttonText.textContent = 'Get AI Call';
            // TODO: Stop microphone capture here
        };
    }
    
    // Initial log
    log('Calling Buddy Web initialized. Ready to make calls.');
}); 