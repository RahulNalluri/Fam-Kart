import {
  getRecordingPermissionsAsync,
  requestRecordingPermissionsAsync,
} from "expo-audio";

import { MicrophonePermissionGateway } from "./microphonePermissions";

export const expoMicrophonePermissionGateway: MicrophonePermissionGateway = {
  get: getRecordingPermissionsAsync,
  request: requestRecordingPermissionsAsync,
};
