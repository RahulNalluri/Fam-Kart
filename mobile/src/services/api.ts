import axios from "axios";

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export type HealthResponse = {
  status: "healthy";
  service: string;
  version: string;
};

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 5000,
});

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get<HealthResponse>("/api/v1/health");
  return response.data;
}

export default api;
