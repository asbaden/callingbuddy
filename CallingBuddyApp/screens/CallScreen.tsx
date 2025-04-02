import React, { useState } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, TextInput, Alert, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../App';
import axios from 'axios';
import { TWILIO_PHONE_NUMBER, BACKEND_URL } from '../utils/config';

type CallScreenNavigationProp = NativeStackNavigationProp<RootStackParamList, 'Call'>;

export default function CallScreen() {
  const navigation = useNavigation<CallScreenNavigationProp>();
  const [phoneNumber, setPhoneNumber] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const initiateCall = async () => {
    // Simple validation
    if (!phoneNumber || phoneNumber.length < 10) {
      Alert.alert('Invalid Number', 'Please enter a valid phone number');
      return;
    }

    setIsLoading(true);

    try {
      // Request the Twilio service to call your number
      const response = await axios.post(`${BACKEND_URL}/call-user`, {
        to: phoneNumber,
      });

      Alert.alert(
        'Call Initiated',
        'You will receive a call from our AI assistant shortly.',
        [{ text: 'OK' }]
      );
    } catch (error) {
      console.error('Error initiating call:', error);
      Alert.alert(
        'Error',
        'There was a problem initiating the call. Please try again later.',
        [{ text: 'OK' }]
      );
    } finally {
      setIsLoading(false);
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
      
      <Text style={styles.directCallText}>
        Or call our assistant directly at: {TWILIO_PHONE_NUMBER}
      </Text>
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
}); 