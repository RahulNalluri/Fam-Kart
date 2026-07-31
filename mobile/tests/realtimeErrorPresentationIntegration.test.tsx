import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { ReactNode } from "react";
import { AppStateStatus, Button, View } from "react-native";

import { RealtimeStatusNotice } from "../src/components/RealtimeStatusNotice";
import {
  HouseholdRealtimeClientFactory,
  HouseholdRealtimeConnection,
  RealtimeAppState,
  useHouseholdRealtime,
} from "../src/hooks/useHouseholdRealtime";
import { useRealtimeStatusNotice } from "../src/hooks/useRealtimeStatusNotice";
import {
  HouseholdRealtimeClientOptions,
  RealtimeCloseDetails,
  classifyRealtimeClose,
} from "../src/services/realtime";

const householdId = "11111111-1111-4111-8111-111111111111";

class FakeAppState implements RealtimeAppState {
  private readonly listeners = new Set<(state: AppStateStatus) => void>();

  constructor(public currentState: AppStateStatus) {}

  addEventListener(
    _type: "change",
    listener: (state: AppStateStatus) => void,
  ): { remove(): void } {
    this.listeners.add(listener);
    return { remove: () => this.listeners.delete(listener) };
  }

  transitionTo(state: AppStateStatus): void {
    this.currentState = state;
    this.listeners.forEach((listener) => listener(state));
  }
}

class FakeRealtimeClient implements HouseholdRealtimeConnection {
  readonly connect = jest.fn();
  readonly disconnect = jest.fn();

  constructor(readonly options: HouseholdRealtimeClientOptions) {}

  reportClose(details: RealtimeCloseDetails): void {
    this.options.onCloseOutcome?.(classifyRealtimeClose(details));
  }

  reportReconnect(): void {
    this.options.onReconnect?.();
  }
}

type RealtimePresentationHarnessProps = {
  appState: RealtimeAppState;
  clientFactory: HouseholdRealtimeClientFactory;
  onAuthenticationRequired?: () => void;
};

function RealtimePresentationHarness({
  appState,
  clientFactory,
  onAuthenticationRequired,
}: RealtimePresentationHarnessProps) {
  const notice = useRealtimeStatusNotice();
  useHouseholdRealtime({
    householdId,
    accessToken: "access-token",
    appState,
    clientFactory,
    onAuthenticationRequired,
    onCloseOutcome: notice.showOutcome,
    onRecovered: notice.handleRecovered,
  });

  return (
    <View>
      <RealtimeStatusNotice outcome={notice.outcome} />
      <Button title="Clear test notice" onPress={notice.clearOutcome} />
    </View>
  );
}

function buildHarness(initialAppState: AppStateStatus = "active") {
  const appState = new FakeAppState(initialAppState);
  const clients: FakeRealtimeClient[] = [];
  const clientFactory: HouseholdRealtimeClientFactory = jest.fn((options) => {
    const client = new FakeRealtimeClient(options);
    clients.push(client);
    return client;
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return { appState, clientFactory, clients, queryClient, wrapper };
}

describe("real-time error presentation integration", () => {
  it("shows a temporary warning and removes it after recovery", () => {
    const harness = buildHarness();
    const { unmount } = render(
      <RealtimePresentationHarness
        appState={harness.appState}
        clientFactory={harness.clientFactory}
      />,
      { wrapper: harness.wrapper },
    );

    act(() =>
      harness.clients[0].reportClose({
        code: 1013,
        reason: "Real-time service unavailable.",
      }),
    );

    expect(
      screen.getByText("Real-time updates are temporarily unavailable. Reconnecting."),
    ).toBeTruthy();
    expect(screen.queryByText("1013")).toBeNull();
    expect(screen.queryByText("Real-time service unavailable.")).toBeNull();

    act(() => harness.clients[0].reportReconnect());

    expect(screen.queryByRole("alert")).toBeNull();
    unmount();
    harness.queryClient.clear();
  });

  it("keeps a permanent warning until its owning action clears it", () => {
    const harness = buildHarness();
    const onAuthenticationRequired = jest.fn();
    const { unmount } = render(
      <RealtimePresentationHarness
        appState={harness.appState}
        clientFactory={harness.clientFactory}
        onAuthenticationRequired={onAuthenticationRequired}
      />,
      { wrapper: harness.wrapper },
    );

    act(() =>
      harness.clients[0].reportClose({
        code: 4401,
        reason: "Authentication required.",
      }),
    );
    expect(onAuthenticationRequired).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText("Your session has expired. Please sign in again."),
    ).toBeTruthy();

    act(() => harness.clients[0].reportReconnect());
    expect(
      screen.getByText("Your session has expired. Please sign in again."),
    ).toBeTruthy();

    fireEvent.press(screen.getByRole("button", { name: "Clear test notice" }));
    expect(screen.queryByRole("alert")).toBeNull();
    unmount();
    harness.queryClient.clear();
  });

  it("does not show normal or late background closures", () => {
    const harness = buildHarness();
    const { unmount } = render(
      <RealtimePresentationHarness
        appState={harness.appState}
        clientFactory={harness.clientFactory}
      />,
      { wrapper: harness.wrapper },
    );

    act(() =>
      harness.clients[0].reportClose({ code: 1000, reason: "Normal closure." }),
    );
    expect(screen.queryByRole("alert")).toBeNull();

    act(() => harness.appState.transitionTo("background"));
    act(() => harness.clients[0].reportClose({ code: 1006, reason: "Network lost." }));
    expect(screen.queryByRole("alert")).toBeNull();
    unmount();
    harness.queryClient.clear();
  });
});
