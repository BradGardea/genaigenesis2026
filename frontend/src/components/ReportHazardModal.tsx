import { useState } from "react";
import { Modal, Pressable, Text, TextInput, View } from "react-native";
import { Coordinate } from "../types/domain";
import { reportHazard } from "../services/api";

const HAZARD_TYPES = ["wildfire", "flood", "roadblock", "chemical", "other"] as const;

interface Props {
  visible: boolean;
  onClose: () => void;
  currentLocation: Coordinate | null;
}

export function ReportHazardModal({ visible, onClose, currentLocation }: Props) {
  const [selectedType, setSelectedType] = useState<string>("roadblock");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!currentLocation) return;
    setSubmitting(true);
    try {
      await reportHazard(selectedType, currentLocation, description);
      setDescription("");
      onClose();
    } catch {
      // Silently fail for MVP — could add error state
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide">
      <View className="flex-1 justify-end bg-black/50">
        <View className="rounded-t-3xl bg-crisis-panel p-6">
          <Text className="mb-4 text-xl font-bold text-crisis-text">Report Hazard</Text>

          <Text className="mb-2 text-sm text-crisis-muted">Hazard Type</Text>
          <View className="mb-4 flex-row flex-wrap gap-2">
            {HAZARD_TYPES.map((type) => (
              <Pressable
                key={type}
                onPress={() => setSelectedType(type)}
                className={`rounded-full px-4 py-2 ${
                  selectedType === type ? "bg-crisis-danger" : "bg-black/30"
                }`}
              >
                <Text className="text-sm capitalize text-crisis-text">{type}</Text>
              </Pressable>
            ))}
          </View>

          <Text className="mb-2 text-sm text-crisis-muted">Description (optional)</Text>
          <TextInput
            className="mb-4 rounded-xl bg-black/30 p-3 text-crisis-text"
            placeholder="What do you see?"
            placeholderTextColor="#9fb0cc"
            value={description}
            onChangeText={setDescription}
            multiline
          />

          <View className="flex-row gap-3">
            <Pressable
              onPress={onClose}
              className="flex-1 rounded-xl bg-black/30 p-3"
            >
              <Text className="text-center text-crisis-muted">Cancel</Text>
            </Pressable>
            <Pressable
              onPress={handleSubmit}
              disabled={submitting || !currentLocation}
              className="flex-1 rounded-xl bg-crisis-danger p-3"
            >
              <Text className="text-center font-semibold text-crisis-text">
                {submitting ? "Reporting..." : "Report"}
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}
