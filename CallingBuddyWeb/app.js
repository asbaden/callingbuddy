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
        
        log(`Initiating call to: ${formattedNumber}`);
        log(`Sending request to: ${BACKEND_URL}/call-user`);
        
        try {
            const response = await fetch(`${BACKEND_URL}/call-user`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ to: formattedNumber })
            });
            
            log(`Received status: ${response.status}`);
            
            const data = await response.text();
            log(`Response: ${data}`);
            
            // Try to parse JSON response
            let jsonData;
            try {
                jsonData = JSON.parse(data);
                log(`Parsed JSON: ${JSON.stringify(jsonData)}`);
            } catch (e) {
                log(`Not JSON data: ${data}`);
            }
            
            if (response.ok) {
                // Success
                if (jsonData && jsonData.call_sid) {
                    showResult(`Call initiated successfully! You will receive a call at ${formattedNumber} shortly.`);
                    log(`Call SID: ${jsonData.call_sid}`);
                } else {
                    showResult(`Call initiated successfully!`);
                }
                
                // Clear input
                phoneNumberInput.value = '';
            } else {
                // Error
                const errorMessage = (jsonData && jsonData.error) 
                    ? jsonData.error 
                    : `Error: ${response.status} ${response.statusText}`;
                    
                showResult(errorMessage, false);
                log(`Error: ${errorMessage}`);
            }
        } catch (error) {
            // Network error
            log(`Fetch error: ${error.message}`);
            showResult(`Network error: ${error.message}. Please try again later.`, false);
        } finally {
            // Reset button state
            callButton.disabled = false;
            spinner.classList.add('hidden');
            buttonText.textContent = 'Get AI Call';
        }
    }
    
    // Initial log
    log('Calling Buddy Web initialized. Ready to make calls.');
}); 