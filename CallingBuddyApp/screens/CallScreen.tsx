import React, { useState } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, TextInput, Alert, ActivityIndicator, Linking } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../App';
import * as ExpoLinking from 'expo-linking';
import { TWILIO_PHONE_NUMBER } from '../utils/config';

type CallScreenNavigationProp = NativeStackNavigationProp<RootStackParamList, 'Call'>;

export default function CallScreen() {
  const navigation = useNavigation<CallScreenNavigationProp>();
  const [isLoading, setIsLoading] = useState(false);

  // Direct call to Twilio number
  const callDirectly = async () => {
    setIsLoading(true);
    
    try {
      const telUrl = `tel:${TWILIO_PHONE_NUMBER}`;
      const canOpen = await ExpoLinking.canOpenURL(telUrl);
      
      if (canOpen) {
        await ExpoLinking.openURL(telUrl);
      } else {
        Alert.alert(
          'Cannot Make Call',
          'Your device cannot make phone calls. Try using a physical device instead of a simulator.',
          [{ text: 'OK' }]
        );
      }
    } catch (error) {
      console.error('Error making direct call:', error);
      Alert.alert(
        'Error',
        'There was a problem making the call. Please try again.',
        [{ text: 'OK' }]
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Call AI Assistant</Text>
      
      <View style={styles.infoCard}>
        <Text style={styles.infoTitle}>How to use</Text>
        <Text style={styles.infoText}>
          Call our Twilio number directly to speak with our AI assistant powered by OpenAI's Realtime API.
        </Text>
        <Text style={styles.infoText}>
          When connected, you can have a natural conversation with the AI, ask questions, or just chat!
        </Text>
      </View>
      
      <View style={styles.phoneNumberContainer}>
        <Text style={styles.phoneNumberLabel}>Call this number:</Text>
        <Text style={styles.phoneNumber}>{TWILIO_PHONE_NUMBER}</Text>
      </View>
      
      <TouchableOpacity 
        style={styles.callButton}
        onPress={callDirectly}
        disabled={isLoading}
      >
        {isLoading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.callButtonText}>Call AI Assistant</Text>
        )}
      </TouchableOpacity>
      
      <Text style={styles.noteSectionTitle}>Notes:</Text>
      <View style={styles.noteContainer}>
        <Text style={styles.noteText}>• Works best on physical devices</Text>
        <Text style={styles.noteText}>• Standard call rates may apply</Text>
        <Text style={styles.noteText}>• First response may take a few seconds</Text>
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
    marginBottom: 25,
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
  phoneNumberContainer: {
    alignItems: 'center',
    marginBottom: 25,
  },
  phoneNumberLabel: {
    fontSize: 16,
    color: '#555',
    marginBottom: 8,
  },
  phoneNumber: {
    fontSize: 26,
    fontWeight: 'bold',
    color: '#3498db',
  },
  callButton: {
    backgroundColor: '#3498db',
    paddingVertical: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 30,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
    elevation: 2,
  },
  callButtonText: {
    color: 'white',
    fontSize: 18,
    fontWeight: '600',
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