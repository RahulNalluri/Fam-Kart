import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import { ReactNode } from "react";
import { AppState } from "react-native";

import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import {
  HouseholdRealtimeClientFactory,
  useHouseholdRealtime,
} from "../src/hooks/useHouseholdRealtime";
import {
  HouseholdRealtimeClient,
  RealtimeCloseDetails,
  RealtimeSocket,
  RealtimeSocketFactory,
} from "../src/services/realtime";

const householdId = "11111111-1111-4111-8111-111111111111";
const otherHouseholdId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const itemId = "44444444-4444-4444-8444-444444444444";

function buildRawEvent({
  eventId = "55555555-5555-4555-8555-555555555555",
  eventHouseholdId = householdId,
  sequenceNumber = 1,
}: {
  eventId?: string;
  eventHouseholdId?: string;
  sequenceNumber?: number;
} = {}): string {
  return JSON.stringify({
    schema_version: 1,
    event_id: eventId,
    event_type: "grocery.item_added",
    household_id: eventHouseholdId,
    occurred_at: "2026-07-30T12:00:00Z",
    payload: {
      shopping_session_id: sessionId,
      grocery_item_id: itemId,
      actor_user_id: "66666666-6666-4666-8666-666666666666",
      item_name: "Milk",
      sequence_number: sequenceNumber,
    },
  });
}

class FakeSocket implements RealtimeSocket {
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((details: RealtimeCloseDetails) => void) | null = null;
  close = jest.fn<void, [number?, string?]>();
}

function buildHarness() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const sockets: FakeSocket[] = [];
  const socketFactory: RealtimeSocketFactory = jest.fn(() => {
    const socket = new FakeSocket();
    sockets.push(socket);
    return socket;
  });
  const clientFactory: HouseholdRealtimeClientFactory = jest.fn(
    (options) =>
      new HouseholdRealtimeClient({
        ...options,
        socketFactory,
        reconnectInitialDelayMs: 100,
        reconnectMaxDelayMs: 400,
      }),
  );
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return { queryClient, sockets, socketFactory, clientFactory, wrapper };
}

describe("complete mobile real-time workflow", () => {
  beforeEach(() => {
    AppState.currentState = "active";
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("validates raw WebSocket JSON and synchronizes React Query", async () => {
    const { queryClient, sockets, clientFactory, wrapper } = buildHarness();
    const itemsKey = groceryQueryKeys.items(householdId, sessionId);
    const activityKey = groceryQueryKeys.activity(householdId, sessionId);
    queryClient.setQueryData(itemsKey, ["Milk"]);
    queryClient.setQueryData(activityKey, []);
    const { result, unmount } = renderHook(
      () =>
        useHouseholdRealtime({
          householdId,
          accessToken: "access-token",
          clientFactory,
        }),
      { wrapper },
    );

    act(() => sockets[0].onopen?.());
    expect(result.current).toBe("connected");
    act(() => sockets[0].onmessage?.({ data: buildRawEvent() }));

    await waitFor(() => {
      expect(queryClient.getQueryState(itemsKey)?.isInvalidated).toBe(true);
      expect(queryClient.getQueryState(activityKey)?.isInvalidated).toBe(true);
    });
    unmount();
    queryClient.clear();
  });

  it("rejects malformed and cross-household raw messages before caching", () => {
    const { queryClient, sockets, clientFactory, wrapper } = buildHarness();
    const invalidateQueries = jest.spyOn(queryClient, "invalidateQueries");
    const { unmount } = renderHook(
      () =>
        useHouseholdRealtime({
          householdId,
          accessToken: "access-token",
          clientFactory,
        }),
      { wrapper },
    );

    act(() => sockets[0].onmessage?.({ data: "not-json" }));
    act(() =>
      sockets[0].onmessage?.({
        data: buildRawEvent({ eventHouseholdId: otherHouseholdId }),
      }),
    );

    expect(invalidateQueries).not.toHaveBeenCalled();
    unmount();
    queryClient.clear();
  });

  it("applies duplicate, stale, and sequence-gap rules to raw messages", () => {
    const { queryClient, sockets, clientFactory, wrapper } = buildHarness();
    const invalidateQueries = jest.spyOn(queryClient, "invalidateQueries");
    const { unmount } = renderHook(
      () =>
        useHouseholdRealtime({
          householdId,
          accessToken: "access-token",
          clientFactory,
        }),
      { wrapper },
    );
    const baseline = buildRawEvent({ sequenceNumber: 3 });

    act(() => sockets[0].onmessage?.({ data: baseline }));
    expect(invalidateQueries).toHaveBeenCalledTimes(2);
    invalidateQueries.mockClear();

    act(() => sockets[0].onmessage?.({ data: baseline }));
    act(() =>
      sockets[0].onmessage?.({
        data: buildRawEvent({
          eventId: "77777777-7777-4777-8777-777777777777",
          sequenceNumber: 2,
        }),
      }),
    );
    expect(invalidateQueries).not.toHaveBeenCalled();

    act(() =>
      sockets[0].onmessage?.({
        data: buildRawEvent({
          eventId: "88888888-8888-4888-8888-888888888888",
          sequenceNumber: 6,
        }),
      }),
    );
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: groceryQueryKeys.session(householdId, sessionId),
    });
    unmount();
    queryClient.clear();
  });

  it("recovers household data and resets ordering after reconnection", () => {
    jest.useFakeTimers();
    const { queryClient, sockets, clientFactory, wrapper } = buildHarness();
    const invalidateQueries = jest.spyOn(queryClient, "invalidateQueries");
    const { result, unmount } = renderHook(
      () =>
        useHouseholdRealtime({
          householdId,
          accessToken: "access-token",
          clientFactory,
        }),
      { wrapper },
    );
    act(() => sockets[0].onopen?.());
    act(() => sockets[0].onmessage?.({ data: buildRawEvent({ sequenceNumber: 5 }) }));
    invalidateQueries.mockClear();

    act(() => sockets[0].onclose?.({ code: 1013, reason: "Try again later." }));
    expect(result.current).toBe("reconnecting");
    act(() => jest.advanceTimersByTime(100));
    expect(sockets).toHaveLength(2);
    act(() => sockets[1].onopen?.());

    expect(result.current).toBe("connected");
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: groceryQueryKeys.household(householdId),
    });
    invalidateQueries.mockClear();

    act(() =>
      sockets[1].onmessage?.({
        data: buildRawEvent({
          eventId: "77777777-7777-4777-8777-777777777777",
          sequenceNumber: 4,
        }),
      }),
    );
    expect(invalidateQueries).toHaveBeenCalledTimes(2);
    unmount();
    queryClient.clear();
  });
});
