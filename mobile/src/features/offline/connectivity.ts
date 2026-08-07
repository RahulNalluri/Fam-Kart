import * as Network from "expo-network";

export type ConnectivityStatus = "unknown" | "offline" | "online";

export type ConnectivityMonitor = Readonly<{
  getCurrentStatus(): Promise<ConnectivityStatus>;
  subscribe(listener: (status: ConnectivityStatus) => void): () => void;
}>;

export function mapNetworkState(
  state: Pick<Network.NetworkState, "type" | "isConnected" | "isInternetReachable">,
): ConnectivityStatus {
  if (
    state.type === Network.NetworkStateType.NONE ||
    state.isConnected === false ||
    state.isInternetReachable === false
  ) {
    return "offline";
  }

  if (state.isConnected === true) {
    return "online";
  }

  return "unknown";
}

export class ExpoConnectivityMonitor implements ConnectivityMonitor {
  async getCurrentStatus(): Promise<ConnectivityStatus> {
    return mapNetworkState(await Network.getNetworkStateAsync());
  }

  subscribe(listener: (status: ConnectivityStatus) => void): () => void {
    const subscription = Network.addNetworkStateListener((state) => {
      listener(mapNetworkState(state));
    });
    return () => subscription.remove();
  }
}
