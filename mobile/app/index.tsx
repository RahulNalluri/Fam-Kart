import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { getHealth } from "../src/services/api";

type BackendStatus = "loading" | "connected" | "unavailable";

export default function HomeScreen() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("loading");

  useEffect(() => {
    let isMounted = true;

    async function checkBackend() {
      try {
        await getHealth();
        if (isMounted) {
          setBackendStatus("connected");
        }
      } catch {
        if (isMounted) {
          setBackendStatus("unavailable");
        }
      }
    }

    void checkBackend();

    return () => {
      isMounted = false;
    };
  }, []);

  const statusText =
    backendStatus === "connected"
      ? "Connected"
      : backendStatus === "unavailable"
        ? "Unavailable"
        : "Checking...";

  return (
    <View style={styles.container}>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          FamilyKart AI
        </Text>
        <Text style={styles.description}>
          Shared shopping made simple for every family.
        </Text>
        <View
          accessibilityLabel={`Backend status: ${statusText}`}
          style={styles.statusRow}
        >
          {backendStatus === "loading" ? (
            <ActivityIndicator accessibilityLabel="Checking backend status" />
          ) : null}
          <Text style={styles.status}>Backend status: {statusText}</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    backgroundColor: "#F7FAF7",
    flex: 1,
    justifyContent: "center",
    padding: 24,
  },
  content: {
    maxWidth: 420,
    width: "100%",
  },
  description: {
    color: "#3E5145",
    fontSize: 18,
    lineHeight: 26,
    marginTop: 12,
  },
  status: {
    color: "#1E3528",
    fontSize: 16,
    fontWeight: "600",
  },
  statusRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    marginTop: 28,
    minHeight: 32,
  },
  title: {
    color: "#123524",
    fontSize: 36,
    fontWeight: "800",
  },
});
