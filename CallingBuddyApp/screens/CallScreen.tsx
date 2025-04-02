import React, { useState, useEffect } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, TextInput, Alert, ActivityIndicator, Platform } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../App';
import axios from 'axios';
import { BACKEND_URL } from '../utils/config';

type CallScreenNavigationProp = NativeStackNavigationProp<RootStackParamList, 'Call'>;

// Create axios instance with configuration for iOS simulator compatibility
const api = axios.create({
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
  // Disable certificate validation for simulator (development only)
  ...(Platform.OS === 'ios' && __DEV__ ? { 
    validateStatus: () => true 
  } : {})
});

export default function CallScreen() {
  const navigation = useNavigation<CallScreenNavigationProp>();
  const [phoneNumber, setPhoneNumber] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [serverStatus, setServerStatus] = useState<'unknown' | 'up' | 'down'>('unknown');

  // Check server status on component mount
  useEffect(() => {
    const checkServer = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/`, { 
          method: 'GET',
          headers: { 'Accept': 'application/json' },
        });
        if (response.ok) {
          console.log('Server is up!');
          setServerStatus('up');
        } else {
          console.log('Server returned error:', response.status);
          setServerStatus('down');
        }
      } catch (error) {
        console.log('Error checking server:', error);
        setServerStatus('down');
      }
    };
    
    checkServer();
  }, []);

  const initiateCall = async () => {
    // Simple validation
    if (!phoneNumber || phoneNumber.length < 10) {
      Alert.alert('Invalid Number', 'Please enter a valid phone number with country code (e.g., +1234567890)');
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      console.log(`Making request to: ${BACKEND_URL}/call-user`);
      
      // Try using fetch instead of axios (sometimes works better in simulator)
      const response = await fetch(`${BACKEND_URL}/call-user`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ to: phoneNumber }),
      });
      
      if (!response.ok) {
        throw new Error(`Server returned ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('Response:', data);
      
      Alert.alert(
        'Call Initiated',
        'You will receive a call from our AI assistant shortly.',
        [{ text: 'OK' }]
      );
    } catch (error: any) {
      console.error('Error initiating call:', error);
      
      let errorMsg = 'There was a problem initiating the call.';
      if (error.message) {
        errorMsg += ` Error: ${error.message}`;
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
    <View style={styles.container}>
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
          <ActivityIndicator color="#fff" />
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

      <Text style={styles.noteSectionTitle}>Notes:</Text>
      <View style={styles.noteContainer}>
        <Text style={styles.noteText}>• First response may take a few seconds</Text>
        <Text style={styles.noteText}>• Make sure your phone number is correct</Text>
        <Text style={styles.noteText}>• Using a physical device may work better than the simulator</Text>
      </View>
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
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 25,
    textAlign: 'center',
    color: '#2c3e50',
  },
  infoCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    marginBottom: 15,
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
    alignItems: 'center',
  },
  serverStatusText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#3498db',
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
  callButton: {
    backgroundColor: '#3498db',
    paddingVertical: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 20,
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
  noteSectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
    color: '#555',
  },
  noteContainer: {
    backgroundColor: '#f0f7ff',
    padding: 15,
    borderRadius: 8,
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