import * as Network from "expo-network";

import {
  ExpoConnectivityMonitor,
  mapNetworkState,
} from "../src/features/offline/connectivity";

jest.mock("expo-network", () => ({
  NetworkStateType: { NONE: "NONE", UNKNOWN: "UNKNOWN", WIFI: "WIFI" },
  getNetworkStateAsync: jest.fn(),
  addNetworkStateListener: jest.fn(),
}));

const getNetworkStateAsync = Network.getNetworkStateAsync as jest.MockedFunction<
  typeof Network.getNetworkStateAsync
>;
const addNetworkStateListener = Network.addNetworkStateListener as jest.MockedFunction<
  typeof Network.addNetworkStateListener
>;

describe("offline connectivity", () => {
  beforeEach(() => jest.clearAllMocks());

  it.each([
    [{ type: Network.NetworkStateType.NONE }, "offline"],
    [{ isConnected: false }, "offline"],
    [{ isConnected: true, isInternetReachable: false }, "offline"],
    [{ isConnected: true, isInternetReachable: true }, "online"],
    [{ isConnected: true }, "online"],
    [{ type: Network.NetworkStateType.UNKNOWN }, "unknown"],
  ] as const)("maps network state %p to %s", (state, expected) => {
    expect(mapNetworkState(state)).toBe(expected);
  });

  it("reads and subscribes through Expo Network with removable cleanup", async () => {
    const remove = jest.fn();
    let nativeListener: ((state: Network.NetworkState) => void) | undefined;
    getNetworkStateAsync.mockResolvedValue({
      type: Network.NetworkStateType.WIFI,
      isConnected: true,
      isInternetReachable: true,
    });
    addNetworkStateListener.mockImplementation((listener) => {
      nativeListener = listener;
      return { remove };
    });
    const monitor = new ExpoConnectivityMonitor();
    const listener = jest.fn();

    await expect(monitor.getCurrentStatus()).resolves.toBe("online");
    const unsubscribe = monitor.subscribe(listener);
    nativeListener?.({ type: Network.NetworkStateType.NONE, isConnected: false });
    expect(listener).toHaveBeenCalledWith("offline");

    unsubscribe();
    expect(remove).toHaveBeenCalledTimes(1);
  });
});
