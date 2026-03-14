import "./global.css";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AppTabs } from "./src/navigation/AppTabs";
import { DisasterDemoProvider } from "./src/state/DisasterDemoContext";

export default function App() {
  return (
    <SafeAreaProvider>
      <DisasterDemoProvider>
        <AppTabs />
      </DisasterDemoProvider>
      <StatusBar style="light" />
    </SafeAreaProvider>
  );
}
