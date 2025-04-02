import React, { useState, useEffect } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, TextInput, Alert, ActivityIndicator, Platform, ScrollView } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../App';
import { BACKEND_URL, NETWORK_CONFIG } from '../utils/config';

type CallScreenNavigationProp = NativeStackNavigationProp<RootStackParamList, 'Call'>;

export default function CallScreen() {
  const navigation = useNavigation<CallScreenNavigationProp>();
  const [phoneNumber, setPhoneNumber] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [serverStatus, setServerStatus] = useState<'unknown' | 'up' | 'down'>('unknown');
  const [debugInfo, setDebugInfo] = useState<string[]>([]);
  const [showDebug, setShowDebug] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  // Add debug log
  const addDebugLog = (message: string) => {
    const timestamp = new Date().toISOString().substring(11, 19);
    console.log(`${timestamp}: ${message}`);
    setDebugInfo(prev => [...prev, `${timestamp}: ${message}`]);
  };

  // Check server status on component mount
  useEffect(() => {
    checkServerStatus();
  }, []);

  // Function to retry a fetch request
  const fetchWithRetry = async (url: string, options: RequestInit, retriesLeft = NETWORK_CONFIG.maxRetries) => {
    addDebugLog(`Fetching ${url} with ${retriesLeft} retries left`);
    
    try {
      const response = await fetch(url, {
        ...options,
        // Set a longer timeout using AbortController
        signal: AbortSignal.timeout(NETWORK_CONFIG.timeout),
      });
      
      addDebugLog(`Response status: ${response.status}`);
      return response;
    } catch (error: any) {
      addDebugLog(`Fetch error: ${error.message}`);
      
      if (retriesLeft <= 0) {
        addDebugLog('No retries left, throwing error');
        throw error;
      }
      
      addDebugLog(`Retrying in ${NETWORK_CONFIG.retryDelay}ms...`);
      await new Promise(resolve => setTimeout(resolve, NETWORK_CONFIG.retryDelay));
      
      setRetryCount(prev => prev + 1);
      return fetchWithRetry(url, options, retriesLeft - 1);
    }
  };

  const checkServerStatus = async () => {
    addDebugLog(`Checking server at ${BACKEND_URL}`);
    try {
      const response = await fetchWithRetry(`${BACKEND_URL}/`, { 
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      });
      
      if (response.ok) {
        const data = await response.json();
        addDebugLog(`Server is up! Response: ${JSON.stringify(data)}`);
        setServerStatus('up');
      } else {
        addDebugLog(`Server returned error: ${response.status}`);
        setServerStatus('down');
      }
    } catch (error: any) {
      addDebugLog(`Final error checking server: ${error.message}`);
      setServerStatus('down');
    }
  };

  const testEndpoint = async () => {
    setIsLoading(true);
    setRetryCount(0);
    addDebugLog(`Testing endpoint: ${BACKEND_URL}/call-user`);

    try {
      const response = await fetchWithRetry(`${BACKEND_URL}/call-user`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ to: '+1234567890' }), // Test number
      });
      
      const textResponse = await response.text();
      addDebugLog(`Response: ${textResponse}`);
      
      Alert.alert('Endpoint Test', 
        `Status: ${response.status}\n\nResponse: ${textResponse}\n\nRetries: ${retryCount}`
      );
    } catch (error: any) {
      addDebugLog(`Final test error: ${error.message}`);
      Alert.alert('Test Error', 
        `Error: ${error.message}\n\nRetries attempted: ${retryCount}`
      );
    } finally {
      setIsLoading(false);
    }
  };

  const initiateCall = async () => {
    // Simple validation
    if (!phoneNumber || phoneNumber.length < 10) {
      Alert.alert('Invalid Number', 'Please enter a valid phone number with country code (e.g., +1234567890)');
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);
    setRetryCount(0);
    addDebugLog(`Initiating call to: ${phoneNumber}`);

    try {
      addDebugLog(`Making request to: ${BACKEND_URL}/call-user`);
      
      const response = await fetchWithRetry(`${BACKEND_URL}/call-user`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ to: phoneNumber }),
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        addDebugLog(`Error response: ${errorText}`);
        throw new Error(`Server returned ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      addDebugLog(`Success response: ${JSON.stringify(data)}`);
      
      Alert.alert(
        'Call Initiated',
        `You will receive a call from our AI assistant shortly.\n\n${retryCount > 0 ? `(Required ${retryCount} retries)` : ''}`,
        [{ text: 'OK' }]
      );
    } catch (error: any) {
      console.error('Error initiating call:', error);
      addDebugLog(`Error caught: ${error.message}`);
      
      let errorMsg = 'There was a problem initiating the call.';
      if (error.message) {
        errorMsg += ` Error: ${error.message}`;
      }
      if (retryCount > 0) {
        errorMsg += `\n\nRetries attempted: ${retryCount}`;
      }
      
      setErrorMessage(errorMsg);
      
      Alert.alert(
        'Error',
        'There was a problem initiating the call. Please try again in a moment.',
        [{ text: 'OK' }]
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>AI Assistant Calls You</Text>
      
      <View style={styles.infoCard}>
        <Text style={styles.infoTitle}>How it works</Text>
        <Text style={styles.infoText}>
          Enter your phone number below and our AI assistant will call you directly.
        </Text>
        <Text style={styles.infoText}>
          When you answer, you can have a natural conversation with the AI, ask questions, or just chat!
        </Text>
      </View>
      
      <View style={styles.serverStatusContainer}>
        <Text style={styles.serverStatusText}>
          Server Status: {
            serverStatus === 'unknown' ? 'Checking...' :
            serverStatus === 'up' ? 'Online ✅' : 'Offline ❌'
          }
        </Text>
        {serverStatus === 'down' && (
          <TouchableOpacity 
            style={styles.retryButton}
            onPress={checkServerStatus}
          >
            <Text style={styles.retryButtonText}>Retry</Text>
          </TouchableOpacity>
        )}
      </View>
      
      <View style={styles.inputContainer}>
        <Text style={styles.label}>Your Phone Number</Text>
        <TextInput
          style={styles.input}
          placeholder="+1 (234) 567-8910"
          keyboardType="phone-pad"
          value={phoneNumber}
          onChangeText={setPhoneNumber}
          maxLength={15}
        />
        <Text style={styles.helpText}>Include country code (e.g., +1 for US)</Text>
      </View>
      
      <TouchableOpacity 
        style={[
          styles.callButton,
          (isLoading || serverStatus === 'down') && styles.callButtonDisabled
        ]}
        onPress={initiateCall}
        disabled={isLoading || serverStatus === 'down'}
      >
        {isLoading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator color="#fff" />
            {retryCount > 0 && (
              <Text style={styles.retryText}>Retry #{retryCount}...</Text>
            )}
          </View>
        ) : (
          <Text style={styles.callButtonText}>Request AI Call</Text>
        )}
      </TouchableOpacity>
      
      {errorMessage && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorTitle}>Error Details:</Text>
          <Text style={styles.errorText}>{errorMessage}</Text>
        </View>
      )}
      
      <View style={styles.debugButtonsContainer}>
        <TouchableOpacity 
          style={styles.debugButton}
          onPress={testEndpoint}
          disabled={isLoading}
        >
          <Text style={styles.debugButtonText}>Test Endpoint</Text>
        </TouchableOpacity>
        
        <TouchableOpacity 
          style={styles.debugButton}
          onPress={() => setShowDebug(!showDebug)}
        >
          <Text style={styles.debugButtonText}>
            {showDebug ? 'Hide Debug Info' : 'Show Debug Info'}
          </Text>
        </TouchableOpacity>
      </View>

      {showDebug && (
        <View style={styles.debugContainer}>
          <Text style={styles.debugTitle}>Debug Logs:</Text>
          <Text style={styles.debugUrl}>Backend URL: {BACKEND_URL}</Text>
          <Text style={styles.debugUrl}>Timeout: {NETWORK_CONFIG.timeout}ms, Max Retries: {NETWORK_CONFIG.maxRetries}</Text>
          {debugInfo.map((log, index) => (
            <Text key={index} style={styles.debugLog}>{log}</Text>
          ))}
        </View>
      )}

      <Text style={styles.noteSectionTitle}>Notes:</Text>
      <View style={styles.noteContainer}>
        <Text style={styles.noteText}>• First response may take a few seconds</Text>
        <Text style={styles.noteText}>• Make sure your phone number is correct</Text>
        <Text style={styles.noteText}>• The app will automatically retry if network issues occur</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 25,
    textAlign: 'center',
    color: '#2c3e50',
    marginTop: 20,
  },
  infoCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    marginBottom: 15,
    marginHorizontal: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  infoTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 12,
    color: '#3498db',
  },
  infoText: {
    fontSize: 15,
    lineHeight: 22,
    color: '#555',
    marginBottom: 10,
  },
  serverStatusContainer: {
    backgroundColor: '#f0f7ff',
    padding: 10,
    borderRadius: 8,
    marginBottom: 20,
    marginHorizontal: 20,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
  },
  serverStatusText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#3498db',
  },
  retryButton: {
    backgroundColor: '#3498db',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 4,
    marginLeft: 10,
  },
  retryButtonText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  inputContainer: {
    marginBottom: 25,
    marginHorizontal: 20,
  },
  label: {
    fontSize: 16,
    marginBottom: 8,
    color: '#555',
  },
  input: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
  },
  helpText: {
    fontSize: 12,
    color: '#777',
    marginTop: 4,
  },
  callButton: {
    backgroundColor: '#3498db',
    paddingVertical: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 20,
    marginHorizontal: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
    elevation: 2,
  },
  callButtonDisabled: {
    backgroundColor: '#a0a0a0',
  },
  callButtonText: {
    color: 'white',
    fontSize: 18,
    fontWeight: '600',
  },
  loadingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  retryText: {
    color: '#fff',
    marginLeft: 10,
    fontSize: 14,
  },
  errorContainer: {
    backgroundColor: '#ffebee',
    padding: 10,
    borderRadius: 5,
    marginBottom: 20,
    marginHorizontal: 20,
    borderWidth: 1,
    borderColor: '#ffcdd2',
  },
  errorTitle: {
    color: '#d32f2f',
    fontWeight: 'bold',
    marginBottom: 5,
  },
  errorText: {
    color: '#d32f2f',
    fontSize: 12,
  },
  debugButtonsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginHorizontal: 20,
    marginBottom: 15,
  },
  debugButton: {
    backgroundColor: '#f1c40f',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 6,
    flex: 0.48,
    alignItems: 'center',
  },
  debugButtonText: {
    color: '#000',
    fontWeight: '600',
  },
  debugContainer: {
    backgroundColor: '#000',
    padding: 12,
    borderRadius: 8,
    marginHorizontal: 20,
    marginBottom: 20,
  },
  debugTitle: {
    color: '#fff',
    fontWeight: 'bold',
    marginBottom: 5,
  },
  debugUrl: {
    color: '#2ecc71',
    marginBottom: 10,
    fontSize: 12,
  },
  debugLog: {
    color: '#ddd',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginBottom: 3,
  },
  noteSectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
    marginHorizontal: 20,
    color: '#555',
  },
  noteContainer: {
    backgroundColor: '#f0f7ff',
    padding: 15,
    borderRadius: 8,
    marginHorizontal: 20,
    marginBottom: 30,
    borderLeftWidth: 4,
    borderLeftColor: '#3498db',
  },
  noteText: {
    fontSize: 14,
    color: '#666',
    marginBottom: 6,
    lineHeight: 20,
  },
}); 