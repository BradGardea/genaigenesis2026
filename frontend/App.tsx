import "./global.css";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AppTabs } from "./src/navigation/AppTabs";

export default function App() {
  return (
    <SafeAreaProvider>
      <AppTabs />
      <StatusBar style="light" />
    </SafeAreaProvider>
  );
}
