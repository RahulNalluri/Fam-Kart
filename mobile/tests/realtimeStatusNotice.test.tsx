import { render, screen } from "@testing-library/react-native";

import { RealtimeStatusNotice } from "../src/components/RealtimeStatusNotice";
import { RealtimeCloseDetails, classifyRealtimeClose } from "../src/services/realtime";

function renderClose(details: RealtimeCloseDetails) {
  return render(<RealtimeStatusNotice outcome={classifyRealtimeClose(details)} />);
}

describe("RealtimeStatusNotice", () => {
  it.each([
    [4401, "Your session has expired. Please sign in again."],
    [4404, "This household is no longer available to your account."],
    [1013, "Real-time updates are temporarily unavailable. Reconnecting."],
    [1006, "The real-time connection was interrupted. Reconnecting."],
  ])("shows readable text for close code %s", (code, expectedMessage) => {
    renderClose({ code: code as number, reason: "Technical server reason." });

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByLabelText(expectedMessage as string)).toBeTruthy();
    expect(screen.getByText(expectedMessage as string)).toBeTruthy();
    expect(screen.queryByText(String(code))).toBeNull();
    expect(screen.queryByText("Technical server reason.")).toBeNull();
  });

  it("renders nothing for a normal closure", () => {
    const { toJSON } = renderClose({ code: 1000, reason: "Normal closure." });

    expect(toJSON()).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders nothing when no close outcome exists", () => {
    const { toJSON } = render(<RealtimeStatusNotice outcome={null} />);

    expect(toJSON()).toBeNull();
  });
});
