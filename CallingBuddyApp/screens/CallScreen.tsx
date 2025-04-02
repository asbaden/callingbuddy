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

  const initiateCall = async () => {
    // Simple validation
    if (!phoneNumber || phoneNumber.length < 10) {
      Alert.alert('Invalid Number', 'Please enter a valid phone number');
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      console.log(`Making request to: ${BACKEND_URL}/call-user`);
      
      // Request the Twilio service to call your number
      const response = await axios.post(`${BACKEND_URL}/call-user`, {
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
        errorMsg += ` Status: ${error.response?.status || 'unknown'}`;
        errorMsg += ` Message: ${error.message}`;
        if (error.response?.data) {
          errorMsg += ` Details: ${JSON.stringify(error.response.data)}`;
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
        style={styles.callButton}
        onPress={initiateCall}
        disabled={isLoading}
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
    marginBottom: 30,
    textAlign: 'center',
    color: '#2c3e50',
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