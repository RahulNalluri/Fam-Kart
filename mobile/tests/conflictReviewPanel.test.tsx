import { fireEvent, render, screen } from "@testing-library/react-native";
import { I18nextProvider } from "react-i18next";

import { ConflictReviewPanel } from "../src/components/ConflictReviewPanel";
import { QueuedOfflineMutation } from "../src/features/offline/localMutationQueueRepository";
import { SupportedLanguage } from "../src/locales/config";
import { createAppI18n } from "../src/locales/i18n";

jest.mock("@expo/vector-icons", () => ({
  Ionicons: () => null,
}));

const mutationId = "11111111-1111-4111-8111-111111111111";
const conflict: QueuedOfflineMutation = {
  mutationId,
  householdId: "22222222-2222-4222-8222-222222222222",
  shoppingSessionId: "33333333-3333-4333-8333-333333333333",
  itemId: "44444444-4444-4444-8444-444444444444",
  operation: "edit",
  payload: {
    name: "Brown rice",
    quantity: "5.000",
    unit: "kg",
    unknown_private_field: "must not render",
  },
  baseUpdatedAt: "2026-08-08T08:00:00Z",
  createdAt: "2026-08-08T08:01:00Z",
  attemptCount: 1,
  status: "requires_review",
  lastErrorCode: "server_conflict",
};

function renderPanel({
  language = "en",
  conflicts = [conflict],
  loading = false,
  resolvingMutationId = null,
  error = null,
  onKeepFamilyVersion = jest.fn(),
  onReviewChange = jest.fn(),
}: Partial<React.ComponentProps<typeof ConflictReviewPanel>> & {
  language?: SupportedLanguage;
} = {}) {
  render(
    <I18nextProvider i18n={createAppI18n(language)}>
      <ConflictReviewPanel
        conflicts={conflicts}
        error={error}
        loading={loading}
        onKeepFamilyVersion={onKeepFamilyVersion}
        onReviewChange={onReviewChange}
        resolvingMutationId={resolvingMutationId}
      />
    </I18nextProvider>,
  );
  return { onKeepFamilyVersion, onReviewChange };
}

describe("ConflictReviewPanel", () => {
  it("shows a readable conflict without technical identifiers or unknown payload", () => {
    renderPanel();

    expect(screen.getByRole("header", { name: "Changes to review" })).toBeTruthy();
    expect(screen.getByText("1 change")).toBeTruthy();
    expect(screen.getByText("Edit: Brown rice")).toBeTruthy();
    expect(
      screen.getByText("A family member changed this item while you were offline."),
    ).toBeTruthy();
    expect(screen.getByText("Quantity: 5.000")).toBeTruthy();
    expect(screen.getByText("Unit: kg")).toBeTruthy();
    expect(screen.queryByText(mutationId)).toBeNull();
    expect(screen.queryByText("server_conflict")).toBeNull();
    expect(screen.queryByText("must not render")).toBeNull();
  });

  it("sends deliberate review and keep-family-version actions", () => {
    const actions = renderPanel();

    fireEvent.press(screen.getByRole("button", { name: "Review change" }));
    fireEvent.press(screen.getByRole("button", { name: "Keep family version" }));

    expect(actions.onReviewChange).toHaveBeenCalledWith(conflict);
    expect(actions.onKeepFamilyVersion).toHaveBeenCalledWith(mutationId);
  });

  it("disables all actions while one reviewed mutation is resolving", () => {
    renderPanel({ resolvingMutationId: mutationId });

    expect(
      screen.getByRole("button", { name: "Review change", disabled: true }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Resolving...", disabled: true }),
    ).toBeTruthy();
  });

  it("shows loading and empty states", () => {
    const { rerender } = render(
      <I18nextProvider i18n={createAppI18n("en")}>
        <ConflictReviewPanel
          conflicts={[]}
          error={null}
          loading
          onKeepFamilyVersion={jest.fn()}
          onReviewChange={jest.fn()}
          resolvingMutationId={null}
        />
      </I18nextProvider>,
    );

    expect(screen.getByText("Loading changes...")).toBeTruthy();
    rerender(
      <I18nextProvider i18n={createAppI18n("en")}>
        <ConflictReviewPanel
          conflicts={[]}
          error={null}
          loading={false}
          onKeepFamilyVersion={jest.fn()}
          onReviewChange={jest.fn()}
          resolvingMutationId={null}
        />
      </I18nextProvider>,
    );
    expect(screen.getByText("No changes need review.")).toBeTruthy();
  });

  it.each([
    ["load_failed", "Changes needing review could not be loaded."],
    ["resolve_failed", "This change could not be resolved. Please try again."],
  ] as const)("shows controlled %s feedback", (error, message) => {
    renderPanel({ conflicts: [], error });

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(message)).toBeTruthy();
    expect(screen.queryByText("No changes need review.")).toBeNull();
  });

  it("renders Telugu conflict labels and actions", () => {
    renderPanel({ language: "te" });

    expect(screen.getByText("పరిశీలించాల్సిన మార్పులు")).toBeTruthy();
    expect(screen.getByText("మార్చు: Brown rice")).toBeTruthy();
    expect(screen.getByText("కుటుంబ వెర్షన్‌ను ఉంచు")).toBeTruthy();
    expect(screen.getByText("మార్పును పరిశీలించు")).toBeTruthy();
  });

  it("uses a supplied current item name for operations without a name payload", () => {
    const completeConflict: QueuedOfflineMutation = {
      ...conflict,
      operation: "complete",
      payload: {},
    };
    render(
      <I18nextProvider i18n={createAppI18n("en")}>
        <ConflictReviewPanel
          conflicts={[completeConflict]}
          error={null}
          getItemName={() => "Fresh milk"}
          loading={false}
          onKeepFamilyVersion={jest.fn()}
          onReviewChange={jest.fn()}
          resolvingMutationId={null}
        />
      </I18nextProvider>,
    );

    expect(screen.getByText("Complete: Fresh milk")).toBeTruthy();
  });
});
