import { useEffect, useRef } from "react";
import { Animated, Easing, Pressable, Text, View } from "react-native";

import { PersonConnectionNode, PersonWithConnections } from "../data/types";

interface ConnectionsKnowledgeGraphProps {
  focalPerson: PersonWithConnections;
  connections: PersonConnectionNode[];
  isDark: boolean;
  onSelectConnection: (node: PersonConnectionNode) => void;
}

const GRAPH_SIZE = 320;
const CENTER_NODE_SIZE = 88;
const CONNECTION_NODE_SIZE = 74;
const CONNECTION_RADIUS = 108;

function EmergencyNode({
  label,
  sublabel,
  isActive,
  isDark,
  left,
  top,
  onPress,
}: {
  label: string;
  sublabel: string;
  isActive: boolean;
  isDark: boolean;
  left: number;
  top: number;
  onPress: () => void;
}) {
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (!isActive) {
      pulse.stopAnimation();
      pulse.setValue(1);
      return;
    }

    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 0.5,
          duration: 650,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 1,
          duration: 650,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();

    return () => loop.stop();
  }, [isActive, pulse]);

  const backgroundColor = isActive
    ? isDark ? "#7f1d1d" : "#fee2e2"
    : isDark ? "#0f172a" : "#ffffff";
  const borderColor = isActive
    ? isDark ? "#f87171" : "#ef4444"
    : isDark ? "#334155" : "#cbd5e1";
  const textColor = isDark ? "#f8fafc" : "#0f172a";
  const sublabelColor = isActive
    ? isDark ? "#fecaca" : "#b91c1c"
    : isDark ? "#cbd5e1" : "#475569";

  return (
    <Animated.View
      style={{
        position: "absolute",
        left,
        top,
        opacity: pulse,
        transform: [{ scale: isActive ? pulse.interpolate({ inputRange: [0.5, 1], outputRange: [0.98, 1.04] }) : 1 }],
      }}
    >
      <Pressable
        accessibilityRole="button"
        onPress={onPress}
        style={{
          width: CONNECTION_NODE_SIZE,
          minHeight: CONNECTION_NODE_SIZE,
          borderRadius: 20,
          borderWidth: 2,
          borderColor,
          backgroundColor,
          paddingHorizontal: 8,
          paddingVertical: 10,
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <Text
          style={{ color: textColor, fontSize: 12, fontWeight: "700", textAlign: "center" }}
          numberOfLines={2}
        >
          {label}
        </Text>
        <Text
          style={{ color: sublabelColor, fontSize: 10, fontWeight: "600", textAlign: "center", marginTop: 4 }}
          numberOfLines={2}
        >
          {sublabel}
        </Text>
      </Pressable>
    </Animated.View>
  );
}

export function ConnectionsKnowledgeGraph({
  focalPerson,
  connections,
  isDark,
  onSelectConnection,
}: ConnectionsKnowledgeGraphProps) {
  const center = GRAPH_SIZE / 2;
  const centerNodeOffset = CENTER_NODE_SIZE / 2;
  const centerNodeColor = isDark ? "#064e3b" : "#d1fae5";
  const centerBorderColor = isDark ? "#34d399" : "#059669";
  const centerTextColor = isDark ? "#ecfdf5" : "#065f46";
  const edgeColor = isDark ? "#475569" : "#cbd5e1";

  return (
    <View
      style={{
        width: GRAPH_SIZE,
        height: GRAPH_SIZE,
        alignSelf: "center",
        marginTop: 16,
        marginBottom: 12,
      }}
    >
      {connections.map((node, index) => {
        const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / Math.max(connections.length, 1));
        const nodeCenterX = center + Math.cos(angle) * CONNECTION_RADIUS;
        const nodeCenterY = center + Math.sin(angle) * CONNECTION_RADIUS;
        const left = nodeCenterX - CONNECTION_NODE_SIZE / 2;
        const top = nodeCenterY - CONNECTION_NODE_SIZE / 2;
        const edgeLength = Math.max(24, Math.hypot(nodeCenterX - center, nodeCenterY - center) - 58);
        const edgeMidpointX = center + (Math.cos(angle) * edgeLength) / 2;
        const edgeMidpointY = center + (Math.sin(angle) * edgeLength) / 2;
        const relationshipLabel = node.emergency_event?.active ? "Needs help" : node.relationship;

        return (
          <View key={node.person.person_id}>
            <View
              style={{
                position: "absolute",
                left: edgeMidpointX - edgeLength / 2,
                top: edgeMidpointY - 1,
                width: edgeLength,
                height: 2,
                backgroundColor: edgeColor,
                transform: [{ rotate: `${(angle * 180) / Math.PI}deg` }],
              }}
            />
            <EmergencyNode
              label={node.person.name}
              sublabel={relationshipLabel}
              isActive={Boolean(node.emergency_event?.active)}
              isDark={isDark}
              left={left}
              top={top}
              onPress={() => onSelectConnection(node)}
            />
          </View>
        );
      })}

      <View
        style={{
          position: "absolute",
          left: center - centerNodeOffset,
          top: center - centerNodeOffset,
          width: CENTER_NODE_SIZE,
          height: CENTER_NODE_SIZE,
          borderRadius: 28,
          borderWidth: 2,
          borderColor: centerBorderColor,
          backgroundColor: centerNodeColor,
          alignItems: "center",
          justifyContent: "center",
          paddingHorizontal: 10,
        }}
      >
        <Text style={{ color: centerTextColor, fontSize: 12, fontWeight: "800", textTransform: "uppercase" }}>
          You
        </Text>
        <Text
          style={{ color: centerTextColor, fontSize: 13, fontWeight: "700", textAlign: "center", marginTop: 4 }}
          numberOfLines={2}
        >
          {focalPerson.name}
        </Text>
      </View>
    </View>
  );
}
