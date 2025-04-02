const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 3000;

// Serve static files from the current directory
app.use(express.static(path.join(__dirname)));

// Routes
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
    console.log(`
======================================================
🌐 CallingBuddy Web is running at http://localhost:${PORT}
======================================================

Access the site:
- From this computer: http://localhost:${PORT}
- From other devices on your network: http://YOUR_IP_ADDRESS:${PORT}

To find your IP address, run: 'ifconfig' or 'ipconfig'
To stop the server: Press Ctrl+C
    `);
}); 