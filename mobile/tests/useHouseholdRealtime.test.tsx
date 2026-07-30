import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import { ReactNode } from "react";

import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import {
  HouseholdRealtimeClientFactory,
  HouseholdRealtimeConnection,
  useHouseholdRealtime,
} from "../src/hooks/useHouseholdRealtime";
import {
  HouseholdRealtimeClientOptions,
  RealtimeConnectionState,
} from "../src/services/realtime";
import { RealtimeEvent } from "../src/types/realtime";

const firstHouseholdId = "11111111-1111-4111-8111-111111111111";
const secondHouseholdId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const itemId = "44444444-4444-4444-8444-444444444444";

function buildEvent(): RealtimeEvent {
  return {
    schema_version: 1,
    event_id: "55555555-5555-4555-8555-555555555555",
    event_type: "grocery.item_added",
    household_id: firstHouseholdId,
    occurred_at: "2026-07-30T12:00:00Z",
    payload: {
      shopping_session_id: sessionId,
      grocery_item_id: itemId,
      actor_user_id: "66666666-6666-4666-8666-666666666666",
      item_name: "Milk",
      sequence_number: 1,
    },
  };
}

class FakeRealtimeClient implements HouseholdRealtimeConnection {
  readonly connect = jest.fn();
  readonly disconnect = jest.fn();

  constructor(readonly options: HouseholdRealtimeClientOptions) {}

  reportState(state: RealtimeConnectionState): void {
    this.options.onStateChange?.(state);
  }

  emit(event: RealtimeEvent): void {
    this.options.onEvent(event);
  }

  reportReconnect(): void {
    this.options.onReconnect?.();
  }
}

function buildHarness() {
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

  return { queryClient, clients, clientFactory, wrapper };
}

describe("useHouseholdRealtime", () => {
  it("stays disconnected until household credentials are available", () => {
    const { clientFactory, wrapper } = buildHarness();

    const { result } = renderHook(
      () =>
        useHouseholdRealtime({
          householdId: null,
          accessToken: null,
          clientFactory,
        }),
      { wrapper },
    );

    expect(result.current).toBe("disconnected");
    expect(clientFactory).not.toHaveBeenCalled();
  });

  it("connects once and exposes client connection state", () => {
    const { clients, clientFactory, wrapper } = buildHarness();
    const { result } = renderHook(
      () =>
        useHouseholdRealtime({
          householdId: firstHouseholdId,
          accessToken: "access-token",
          clientFactory,
        }),
      { wrapper },
    );

    expect(clients).toHaveLength(1);
    expect(clients[0].connect).toHaveBeenCalledTimes(1);
    expect(clients[0].options.householdId).toBe(firstHouseholdId);
    expect(clients[0].options.accessToken).toBe("access-token");

    act(() => clients[0].reportState("connected"));

    expect(result.current).toBe("connected");
  });

  it("synchronizes incoming events with the affected grocery queries", async () => {
    const { queryClient, clients, clientFactory, wrapper } = buildHarness();
    const itemsKey = groceryQueryKeys.items(firstHouseholdId, sessionId);
    const activityKey = groceryQueryKeys.activity(firstHouseholdId, sessionId);
    queryClient.setQueryData(itemsKey, ["Milk"]);
    queryClient.setQueryData(activityKey, []);
    renderHook(
      () =>
        useHouseholdRealtime({
          householdId: firstHouseholdId,
          accessToken: "access-token",
          clientFactory,
        }),
      { wrapper },
    );

    act(() => clients[0].emit(buildEvent()));

    await waitFor(() => {
      expect(queryClient.getQueryState(itemsKey)?.isInvalidated).toBe(true);
      expect(queryClient.getQueryState(activityKey)?.isInvalidated).toBe(true);
    });
    queryClient.clear();
  });

  it("refreshes only the active household after reconnection", async () => {
    const { queryClient, clients, clientFactory, wrapper } = buildHarness();
    const firstKey = groceryQueryKeys.items(firstHouseholdId, sessionId);
    const secondKey = groceryQueryKeys.items(secondHouseholdId, sessionId);
    queryClient.setQueryData(firstKey, ["Milk"]);
    queryClient.setQueryData(secondKey, ["Rice"]);
    renderHook(
      () =>
        useHouseholdRealtime({
          householdId: firstHouseholdId,
          accessToken: "access-token",
          clientFactory,
        }),
      { wrapper },
    );

    act(() => clients[0].reportReconnect());

    await waitFor(() => {
      expect(queryClient.getQueryState(firstKey)?.isInvalidated).toBe(true);
    });
    expect(queryClient.getQueryState(secondKey)?.isInvalidated).toBe(false);
    queryClient.clear();
  });

  it("replaces the client when the active household changes", () => {
    const { clients, clientFactory, wrapper } = buildHarness();
    const { rerender } = renderHook<RealtimeConnectionState, { householdId: string }>(
      ({ householdId }) =>
        useHouseholdRealtime({
          householdId,
          accessToken: "access-token",
          clientFactory,
        }),
      {
        initialProps: { householdId: firstHouseholdId },
        wrapper,
      },
    );

    rerender({ householdId: secondHouseholdId });

    expect(clients).toHaveLength(2);
    expect(clients[0].disconnect).toHaveBeenCalledTimes(1);
    expect(clients[1].connect).toHaveBeenCalledTimes(1);
    expect(clients[1].options.householdId).toBe(secondHouseholdId);
  });

  it("replaces the client when the token changes and disconnects on logout", () => {
    const { clients, clientFactory, wrapper } = buildHarness();
    const { result, rerender } = renderHook<
      RealtimeConnectionState,
      { accessToken: string | null }
    >(
      ({ accessToken }) =>
        useHouseholdRealtime({
          householdId: firstHouseholdId,
          accessToken,
          clientFactory,
        }),
      {
        initialProps: { accessToken: "first-access-token" },
        wrapper,
      },
    );

    rerender({ accessToken: "rotated-access-token" });

    expect(clients).toHaveLength(2);
    expect(clients[0].disconnect).toHaveBeenCalledTimes(1);
    expect(clients[1].options.accessToken).toBe("rotated-access-token");

    rerender({ accessToken: null });

    expect(clients).toHaveLength(2);
    expect(clients[1].disconnect).toHaveBeenCalledTimes(1);
    expect(result.current).toBe("disconnected");
  });

  it("disconnects on unmount and ignores callbacks from the old client", () => {
    const { queryClient, clients, clientFactory, wrapper } = buildHarness();
    const itemsKey = groceryQueryKeys.items(firstHouseholdId, sessionId);
    queryClient.setQueryData(itemsKey, ["Milk"]);
    const { unmount } = renderHook(
      () =>
        useHouseholdRealtime({
          householdId: firstHouseholdId,
          accessToken: "access-token",
          clientFactory,
        }),
      { wrapper },
    );
    const oldClient = clients[0];

    unmount();
    oldClient.emit(buildEvent());
    oldClient.reportReconnect();

    expect(oldClient.disconnect).toHaveBeenCalledTimes(1);
    expect(queryClient.getQueryState(itemsKey)?.isInvalidated).toBe(false);
    queryClient.clear();
  });
});
