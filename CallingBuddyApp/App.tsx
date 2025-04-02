import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import HomeScreen from './screens/HomeScreen';
import CallScreen from './screens/CallScreen';
import AboutScreen from './screens/AboutScreen';

export type RootStackParamList = {
  Home: undefined;
  Call: undefined;
  About: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="auto" />
      <Stack.Navigator initialRouteName="Home">
        <Stack.Screen 
          name="Home" 
          component={HomeScreen} 
          options={{ title: 'Calling Buddy' }} 
        />
        <Stack.Screen 
          name="Call" 
          component={CallScreen} 
          options={{ title: 'Make a Call' }} 
        />
        <Stack.Screen 
          name="About" 
          component={AboutScreen} 
          options={{ title: 'About' }} 
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
