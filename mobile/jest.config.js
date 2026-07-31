module.exports = {
  preset: "jest-expo",
  testMatch: ["**/tests/**/*.test.ts", "**/tests/**/*.test.tsx"],
  transformIgnorePatterns: [
    "node_modules/(?!((jest-)?react-native|@react-native|expo(nent)?|expo-.*|@expo(nent)?/.*|react-native-safe-area-context|react-native-screens)/)",
  ],
};
