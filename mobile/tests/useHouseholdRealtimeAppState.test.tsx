import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react-native";
import { ReactNode } from "react";
import { AppStateStatus } from "react-native";

import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import {
  HouseholdRealtimeClientFactory,
  HouseholdRealtimeConnection,
  RealtimeAppState,
  useHouseholdRealtime,
} from "../src/hooks/useHouseholdRealtime";
import { HouseholdRealtimeClientOptions } from "../src/services/realtime";
import { RealtimeEvent } from "../src/types/realtime";

const householdId = "11111111-1111-4111-8111-111111111111";
const sessionId = "22222222-2222-4222-8222-222222222222";

class FakeAppState implements RealtimeAppState {
  private readonly listeners = new Set<(state: AppStateStatus) => void>();
  readonly removeListener = jest.fn();

  constructor(public currentState: AppStateStatus) {}

  addEventListener(
    type: "change",
    listener: (state: AppStateStatus) => void,
  ): { remove(): void } {
    this.listeners.add(listener);
    return {
      remove: () => {
        this.listeners.delete(listener);
        this.removeListener();
      },
    };
  }

  transitionTo(state: AppStateStatus): void {
    this.currentState = state;
    this.listeners.forEach((listener) => listener(state));
  }

  get listenerCount(): number {
    return this.listeners.size;
  }
}

class FakeRealtimeClient implements HouseholdRealtimeConnection {
  readonly connect = jest.fn();
  readonly disconnect = jest.fn();

  constructor(readonly options: HouseholdRealtimeClientOptions) {}

  emit(event: RealtimeEvent): void {
    this.options.onEvent(event);
  }
}

function buildEvent(): RealtimeEvent {
  return {
    schema_version: 1,
    event_id: "33333333-3333-4333-8333-333333333333",
    event_type: "grocery.item_added",
    household_id: householdId,
    occurred_at: "2026-07-31T12:00:00Z",
    payload: {
      shopping_session_id: sessionId,
      grocery_item_id: "44444444-4444-4444-8444-444444444444",
      actor_user_id: "55555555-5555-4555-8555-555555555555",
      item_name: "Milk",
      sequence_number: 1,
    },
  };
}

function buildHarness(initialState: AppStateStatus) {
  const appState = new FakeAppState(initialState);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const clients: FakeRealtimeClient[] = [];
  const clientFactory: HouseholdRealtimeClientFactory = jest.fn((options) => {
    const client = new FakeRealtimeClient(options);
    clients.push(client);
    return client;
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return { appState, queryClient, clients, clientFactory, wrapper };
}

function renderRealtimeHook(harness: ReturnType<typeof buildHarness>) {
  return renderHook(
    () =>
      useHouseholdRealtime({
        householdId,
        accessToken: "access-token",
        appState: harness.appState,
        clientFactory: harness.clientFactory,
      }),
    { wrapper: harness.wrapper },
  );
}

describe("useHouseholdRealtime AppState lifecycle", () => {
  it("waits in the background and connects with recovery on foreground", () => {
    const harness = buildHarness("background");
    const invalidateQueries = jest.spyOn(harness.queryClient, "invalidateQueries");
    const { result, unmount } = renderRealtimeHook(harness);

    expect(result.current).toBe("disconnected");
    expect(harness.clients[0].connect).not.toHaveBeenCalled();

    act(() => harness.appState.transitionTo("active"));

    expect(harness.clients[0].connect).toHaveBeenCalledTimes(1);
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: groceryQueryKeys.household(householdId),
    });
    unmount();
    harness.queryClient.clear();
  });

  it("disconnects once while backgrounded and avoids duplicate reconnects", () => {
    const harness = buildHarness("active");
    const invalidateQueries = jest.spyOn(harness.queryClient, "invalidateQueries");
    const { result, unmount } = renderRealtimeHook(harness);
    expect(harness.clients[0].connect).toHaveBeenCalledTimes(1);

    act(() => harness.appState.transitionTo("inactive"));
    act(() => harness.appState.transitionTo("background"));

    expect(result.current).toBe("disconnected");
    expect(harness.clients[0].disconnect).toHaveBeenCalledTimes(1);

    act(() => harness.appState.transitionTo("active"));
    act(() => harness.appState.transitionTo("active"));

    expect(harness.clients[0].connect).toHaveBeenCalledTimes(2);
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
    unmount();
    harness.queryClient.clear();
  });

  it("ignores late real-time events while the app is backgrounded", () => {
    const harness = buildHarness("active");
    const itemsKey = groceryQueryKeys.items(householdId, sessionId);
    harness.queryClient.setQueryData(itemsKey, ["Milk"]);
    const { unmount } = renderRealtimeHook(harness);

    act(() => harness.appState.transitionTo("background"));
    act(() => harness.clients[0].emit(buildEvent()));

    expect(harness.queryClient.getQueryState(itemsKey)?.isInvalidated).toBe(false);
    unmount();
    harness.queryClient.clear();
  });

  it("removes the AppState listener and disconnects on unmount", () => {
    const harness = buildHarness("active");
    const { unmount } = renderRealtimeHook(harness);
    expect(harness.appState.listenerCount).toBe(1);

    unmount();
    act(() => harness.appState.transitionTo("background"));
    act(() => harness.appState.transitionTo("active"));

    expect(harness.appState.listenerCount).toBe(0);
    expect(harness.appState.removeListener).toHaveBeenCalledTimes(1);
    expect(harness.clients[0].disconnect).toHaveBeenCalledTimes(1);
    expect(harness.clients[0].connect).toHaveBeenCalledTimes(1);
    harness.queryClient.clear();
  });
});
