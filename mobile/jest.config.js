module.exports = {
  preset: "jest-expo",
  testMatch: ["**/tests/**/*.test.tsx"],
  transformIgnorePatterns: [
    "node_modules/(?!((jest-)?react-native|@react-native|expo(nent)?|@expo(nent)?/.*|expo-modules-core|expo-router|@expo/vector-icons|react-native-safe-area-context|react-native-screens)/)",
  ],
};
