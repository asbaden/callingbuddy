import React, { useState } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, TextInput, Alert, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../App';
import * as ExpoLinking from 'expo-linking';
import axios from 'axios';
import { TWILIO_PHONE_NUMBER, BACKEND_URL } from '../utils/config';

type CallScreenNavigationProp = NativeStackNavigationProp<RootStackParamList, 'Call'>;

export default function CallScreen() {
  const navigation = useNavigation<CallScreenNavigationProp>();
  const [phoneNumber, setPhoneNumber] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [serverStatus, setServerStatus] = useState<'unknown' | 'checking' | 'ready' | 'error'>('unknown');

  // Create axios instance with longer timeout
  const axiosInstance = axios.create({
    timeout: 30000, // 30 seconds
  });

  // Check server status
  const checkServerStatus = async () => {
    setServerStatus('checking');
    setErrorMessage(null);
    
    try {
      const response = await axiosInstance.get(BACKEND_URL);
      console.log('Server status check response:', response.data);
      setServerStatus('ready');
      return true;
    } catch (error) {
      console.error('Error checking server status:', error);
      setServerStatus('error');
      setErrorMessage('Server is not responding. Please try again in a minute.');
      return false;
    }
  };

  const initiateCall = async () => {
    // Simple validation
    if (!phoneNumber || phoneNumber.length < 10) {
      Alert.alert('Invalid Number', 'Please enter a valid phone number');
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    // First check if server is ready
    const isReady = await checkServerStatus();
    if (!isReady) {
      setIsLoading(false);
      Alert.alert(
        'Server Not Ready',
        'Please wake up the server first by clicking the "Wake Up Server" button and wait about 30 seconds.'
      );
      return;
    }

    try {
      console.log(`Making request to: ${BACKEND_URL}/call-user`);
      
      // Request the Twilio service to call your number
      const response = await axiosInstance.post(`${BACKEND_URL}/call-user`, {
        to: phoneNumber,
      });

      console.log('Response:', response.data);
      
      Alert.alert(
        'Call Initiated',
        'You will receive a call from our AI assistant shortly.',
        [{ text: 'OK' }]
      );
    } catch (error: any) {
      console.error('Error initiating call:', error);
      
      // Get more detailed error information
      let errorMsg = 'There was a problem initiating the call.';
      
      if (axios.isAxiosError(error)) {
        if (error.code === 'ECONNABORTED') {
          errorMsg = 'Request timed out. The server might be starting up. Try again in a minute.';
        } else {
          errorMsg += ` Status: ${error.response?.status || 'unknown'}`;
          errorMsg += ` Message: ${error.message}`;
          if (error.response?.data) {
            errorMsg += ` Details: ${JSON.stringify(error.response.data)}`;
          }
        }
      }
      
      setErrorMessage(errorMsg);
      
      Alert.alert(
        'Error',
        'There was a problem initiating the call. See error details below.',
        [{ text: 'OK' }]
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Alternative method - direct call
  const callDirectly = async () => {
    try {
      const telUrl = `tel:${TWILIO_PHONE_NUMBER}`;
      const canOpen = await ExpoLinking.canOpenURL(telUrl);
      
      if (canOpen) {
        await ExpoLinking.openURL(telUrl);
      } else {
        Alert.alert(
          'Cannot Make Call',
          'Your device cannot make phone calls. Try on a physical device.'
        );
      }
    } catch (error) {
      console.error('Error making direct call:', error);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Call AI Assistant</Text>
      
      <View style={styles.serverStatusContainer}>
        <Text style={styles.serverStatusText}>
          Server Status: {
            serverStatus === 'unknown' ? 'Unknown' :
            serverStatus === 'checking' ? 'Checking...' :
            serverStatus === 'ready' ? 'Ready' : 'Not Responding'
          }
        </Text>
        <TouchableOpacity
          style={[
            styles.serverStatusButton,
            serverStatus === 'checking' && styles.serverStatusButtonDisabled
          ]}
          onPress={checkServerStatus}
          disabled={serverStatus === 'checking'}
        >
          <Text style={styles.serverStatusButtonText}>
            {serverStatus === 'checking' ? 'Checking...' : 'Wake Up Server'}
          </Text>
        </TouchableOpacity>
        <Text style={styles.serverTip}>
          Tip: Free servers may take 30-60 seconds to wake up. Click the button above and wait before making a call.
        </Text>
      </View>
      
      <View style={styles.inputContainer}>
        <Text style={styles.label}>Your Phone Number</Text>
        <TextInput
          style={styles.input}
          placeholder="Enter your phone number"
          keyboardType="phone-pad"
          value={phoneNumber}
          onChangeText={setPhoneNumber}
          maxLength={15}
        />
        <Text style={styles.helpText}>Include country code (e.g., +1 for US)</Text>
      </View>
      
      <Text style={styles.infoText}>
        Enter your phone number above and our AI assistant will call you.
      </Text>
      
      <TouchableOpacity 
        style={[
          styles.callButton,
          (isLoading || serverStatus !== 'ready') && styles.callButtonDisabled
        ]}
        onPress={initiateCall}
        disabled={isLoading || serverStatus !== 'ready'}
      >
        {isLoading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.callButtonText}>Get AI Call</Text>
        )}
      </TouchableOpacity>
      
      {errorMessage && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorTitle}>Error Details:</Text>
          <Text style={styles.errorText}>{errorMessage}</Text>
        </View>
      )}
      
      <Text style={styles.separatorText}>OR</Text>
      
      <TouchableOpacity 
        style={[styles.callButton, styles.directCallButton]}
        onPress={callDirectly}
      >
        <Text style={styles.directCallButtonText}>Call Directly: {TWILIO_PHONE_NUMBER}</Text>
      </TouchableOpacity>
      
      <Text style={styles.debugText}>Backend URL: {BACKEND_URL}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: '#f5f5f5',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
    textAlign: 'center',
    color: '#2c3e50',
  },
  serverStatusContainer: {
    backgroundColor: '#fff',
    padding: 15,
    borderRadius: 10,
    marginBottom: 20,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e0e0e0',
  },
  serverStatusText: {
    fontSize: 16,
    marginBottom: 10,
    color: '#555',
  },
  serverStatusButton: {
    backgroundColor: '#4CAF50',
    paddingVertical: 8,
    paddingHorizontal: 15,
    borderRadius: 5,
  },
  serverStatusButtonDisabled: {
    backgroundColor: '#a0a0a0',
  },
  serverStatusButtonText: {
    color: 'white',
    fontWeight: '600',
  },
  serverTip: {
    fontSize: 12,
    color: '#777',
    marginTop: 10,
    textAlign: 'center',
  },
  inputContainer: {
    marginBottom: 25,
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
  infoText: {
    fontSize: 14,
    color: '#777',
    marginBottom: 30,
    textAlign: 'center',
    lineHeight: 20,
  },
  callButton: {
    backgroundColor: '#3498db',
    paddingVertical: 15,
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 20,
  },
  callButtonDisabled: {
    backgroundColor: '#a0a0a0',
  },
  callButtonText: {
    color: 'white',
    fontSize: 18,
    fontWeight: '600',
  },
  directCallText: {
    textAlign: 'center',
    color: '#777',
    fontSize: 15,
  },
  errorContainer: {
    backgroundColor: '#ffebee',
    padding: 10,
    borderRadius: 5,
    marginBottom: 20,
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
  separatorText: {
    textAlign: 'center',
    color: '#777',
    marginVertical: 10,
    fontSize: 14,
    fontWeight: 'bold',
  },
  directCallButton: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#3498db',
  },
  directCallButtonText: {
    color: '#3498db',
    fontSize: 16,
    fontWeight: '600',
  },
  debugText: {
    fontSize: 10,
    color: '#aaa',
    textAlign: 'center',
    marginTop: 20,
  },
}); 