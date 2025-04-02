import React from 'react';
import { StyleSheet, Text, View, ScrollView, TouchableOpacity, Linking } from 'react-native';
import { APP_VERSION } from '../utils/config';

export default function AboutScreen() {
  return (
    <ScrollView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.title}>About Calling Buddy</Text>
        
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>What is Calling Buddy?</Text>
          <Text style={styles.paragraph}>
            Calling Buddy is an AI-powered voice assistant that uses OpenAI's Realtime API
            and Twilio's voice services to create a natural, conversational experience over
            the phone.
          </Text>
        </View>
        
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>How it Works</Text>
          <Text style={styles.paragraph}>
            When you call our Twilio number, your voice is streamed to our server, which
            forwards it to OpenAI's Realtime API. The API processes your speech in real-time
            and responds with natural-sounding voice that's streamed back to your call.
          </Text>
        </View>
        
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Technology Stack</Text>
          <Text style={styles.bulletItem}>• OpenAI Realtime API</Text>
          <Text style={styles.bulletItem}>• Twilio Voice API</Text>
          <Text style={styles.bulletItem}>• Python FastAPI (Backend)</Text>
          <Text style={styles.bulletItem}>• React Native & Expo (Mobile App)</Text>
        </View>
        
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Contact</Text>
          <TouchableOpacity
            onPress={() => Linking.openURL('mailto:contact@example.com')}
          >
            <Text style={styles.link}>contact@example.com</Text>
          </TouchableOpacity>
        </View>
        
        <View style={styles.footer}>
          <Text style={styles.footerText}>© 2024 Calling Buddy</Text>
          <Text style={styles.footerText}>Version {APP_VERSION}</Text>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  content: {
    padding: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 25,
    textAlign: 'center',
    color: '#2c3e50',
  },
  section: {
    marginBottom: 25,
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 18,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 12,
    color: '#3498db',
  },
  paragraph: {
    fontSize: 16,
    lineHeight: 22,
    color: '#555',
  },
  bulletItem: {
    fontSize: 16,
    lineHeight: 24,
    marginLeft: 8,
    color: '#555',
  },
  link: {
    color: '#3498db',
    fontSize: 16,
    textDecorationLine: 'underline',
  },
  footer: {
    marginTop: 30,
    borderTopWidth: 1,
    borderTopColor: '#ddd',
    paddingTop: 20,
    alignItems: 'center',
  },
  footerText: {
    color: '#999',
    fontSize: 14,
    marginBottom: 5,
  },
}); 