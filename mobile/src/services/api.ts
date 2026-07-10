import axios from "axios";

export type HealthResponse = {
  status: "healthy";
  service: string;
  version: string;
};

const api = axios.create({
  baseURL: process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000",
  timeout: 5000,
});

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get<HealthResponse>("/api/v1/health");
  return response.data;
}

export default api;
