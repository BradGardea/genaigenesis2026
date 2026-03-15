import { useEffect, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import {
  ConnectionRelationship,
  createConnection,
  fetchConnections,
  UserConnection
} from "../data";
import { AppTheme } from "../types/theme";

interface ProfileScreenProps {
  theme: AppTheme;
  onThemeChange: (theme: AppTheme) => void;
  fullName: string;
  onFullNameChange: (value: string) => void;
  phoneNumber: string;
  onPhoneNumberChange: (value: string) => void;
  homeArea: string;
  onHomeAreaChange: (value: string) => void;
}

const RELATIONSHIP_OPTIONS: ConnectionRelationship[] = [
  "dependent",
  "guardian",
  "friend",
  "acquaintance"
];

export function ProfileScreen({
  theme,
  onThemeChange,
  fullName,
  onFullNameChange,
  phoneNumber,
  onPhoneNumberChange,
  homeArea,
  onHomeAreaChange
}: ProfileScreenProps) {
  const isDark = theme === "dark";

  const [connectionPhone, setConnectionPhone] = useState("");
  const [relationship, setRelationship] = useState<ConnectionRelationship>("friend");
  const [connections, setConnections] = useState<UserConnection[]>([]);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadConnections() {
      if (phoneNumber.trim().length === 0) {
        setConnections([]);
        return;
      }

      try {
        const nextConnections = await fetchConnections(phoneNumber);

        if (!cancelled) {
          setConnections(nextConnections);
        }
      } catch {
        if (!cancelled) {
          setInfoMessage("Unable to load connections.");
        }
      }
    }

    void loadConnections();

    return () => {
      cancelled = true;
    };
  }, [phoneNumber]);

  const saveConnection = async () => {
    if (phoneNumber.trim().length === 0 || connectionPhone.trim().length === 0) {
      setInfoMessage("Add your phone number and a connection phone first.");
      return;
    }

    try {
      await createConnection({
        ownerPhone: phoneNumber,
        contactPhone: connectionPhone,
        relationship
      });

      const nextConnections = await fetchConnections(phoneNumber);
      setConnections(nextConnections);
      setConnectionPhone("");
      setInfoMessage("Connection added with reciprocal relationship logic.");
    } catch {
      setInfoMessage("Unable to save connection right now.");
    }
  };

  return (
    <View className={`flex-1 px-4 pt-3 ${isDark ? "bg-slate-950" : "bg-slate-100"}`}>
      <Text className={`text-sm ${isDark ? "text-slate-400" : "text-slate-600"}`}>
        Minimal profile setup for personalized alerts.
      </Text>

      <View
        className={`mt-3 rounded-2xl p-4 ${
          isDark ? "border border-slate-700 bg-slate-900" : "border border-slate-300 bg-white"
        }`}
      >
        <Text className={`mb-2 text-xs ${isDark ? "text-slate-300" : "text-slate-600"}`}>
          Theme
        </Text>
        <View className="mb-4 flex-row">
          <Pressable
            className={`mr-2 flex-1 rounded-xl px-3 py-2 ${
              theme === "light" ? "bg-slate-900" : isDark ? "bg-slate-800" : "bg-slate-200"
            }`}
            onPress={() => onThemeChange("light")}
          >
            <Text
              className={`text-center font-semibold ${
                theme === "light" ? "text-white" : isDark ? "text-slate-200" : "text-slate-700"
              }`}
            >
              Light (Default)
            </Text>
          </Pressable>

          <Pressable
            className={`flex-1 rounded-xl px-3 py-2 ${
              theme === "dark" ? "bg-slate-900" : isDark ? "bg-slate-800" : "bg-slate-200"
            }`}
            onPress={() => onThemeChange("dark")}
          >
            <Text
              className={`text-center font-semibold ${
                theme === "dark" ? "text-white" : isDark ? "text-slate-200" : "text-slate-700"
              }`}
            >
              Dark
            </Text>
          </Pressable>
        </View>

        <Text className={`mb-1 text-xs ${isDark ? "text-slate-300" : "text-slate-600"}`}>Full name</Text>
        <TextInput
          className={`mb-3 rounded-xl border px-3 py-2 ${
            isDark
              ? "border-slate-600 bg-slate-800 text-slate-100"
              : "border-slate-300 bg-slate-50 text-slate-900"
          }`}
          onChangeText={onFullNameChange}
          placeholder="Full name"
          placeholderTextColor={isDark ? "#94a3b8" : "#64748b"}
          value={fullName}
        />

        <Text className={`mb-1 text-xs ${isDark ? "text-slate-300" : "text-slate-600"}`}>
          Phone number
        </Text>
        <TextInput
          className={`mb-3 rounded-xl border px-3 py-2 ${
            isDark
              ? "border-slate-600 bg-slate-800 text-slate-100"
              : "border-slate-300 bg-slate-50 text-slate-900"
          }`}
          keyboardType="phone-pad"
          onChangeText={onPhoneNumberChange}
          placeholder="Phone number"
          placeholderTextColor={isDark ? "#94a3b8" : "#64748b"}
          value={phoneNumber}
        />

        <Text className={`mb-1 text-xs ${isDark ? "text-slate-300" : "text-slate-600"}`}>Home area</Text>
        <TextInput
          className={`mb-4 rounded-xl border px-3 py-2 ${
            isDark
              ? "border-slate-600 bg-slate-800 text-slate-100"
              : "border-slate-300 bg-slate-50 text-slate-900"
          }`}
          onChangeText={onHomeAreaChange}
          placeholder="Home area"
          placeholderTextColor={isDark ? "#94a3b8" : "#64748b"}
          value={homeArea}
        />

        <Text className={`mb-1 text-xs ${isDark ? "text-slate-300" : "text-slate-600"}`}>
          Add connection (phone)
        </Text>
        <TextInput
          className={`mb-3 rounded-xl border px-3 py-2 ${
            isDark
              ? "border-slate-600 bg-slate-800 text-slate-100"
              : "border-slate-300 bg-slate-50 text-slate-900"
          }`}
          keyboardType="phone-pad"
          onChangeText={setConnectionPhone}
          placeholder="Connection phone"
          placeholderTextColor={isDark ? "#94a3b8" : "#64748b"}
          value={connectionPhone}
        />

        <Text className={`mb-2 text-xs ${isDark ? "text-slate-300" : "text-slate-600"}`}>
          Relationship
        </Text>
        <View className="mb-4 flex-row flex-wrap">
          {RELATIONSHIP_OPTIONS.map((option) => {
            const selected = relationship === option;
            return (
              <Pressable
                key={option}
                className={`mb-2 mr-2 rounded-full px-3 py-2 ${
                  selected
                    ? isDark
                      ? "bg-slate-100"
                      : "bg-slate-900"
                    : isDark
                      ? "bg-slate-800"
                      : "bg-slate-200"
                }`}
                onPress={() => setRelationship(option)}
              >
                <Text
                  className={`text-xs font-semibold capitalize ${
                    selected
                      ? isDark
                        ? "text-slate-900"
                        : "text-slate-100"
                      : isDark
                        ? "text-slate-300"
                        : "text-slate-700"
                  }`}
                >
                  {option}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Pressable className={`rounded-xl p-3 ${isDark ? "bg-slate-100" : "bg-slate-900"}`} onPress={saveConnection}>
          <Text className={`text-center font-semibold ${isDark ? "text-slate-900" : "text-slate-100"}`}>
            Save profile and add connection
          </Text>
        </Pressable>

        {infoMessage ? (
          <Text className={`mt-3 text-xs ${isDark ? "text-slate-300" : "text-slate-700"}`}>{infoMessage}</Text>
        ) : null}
      </View>
    </View>
  );
}
