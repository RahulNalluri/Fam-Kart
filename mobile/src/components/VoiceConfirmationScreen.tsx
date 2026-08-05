import { Ionicons } from "@expo/vector-icons";
import { useMemo, useState } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import {
  GROCERY_UNITS,
  GroceryUnit,
  isVoiceConfirmationValid,
  normalizeVoiceConfirmationItem,
  validateVoiceConfirmationItem,
  VoiceConfirmationItem,
  VoiceConfirmationSubmitErrorCode,
} from "../features/voice/confirmation";

export type VoiceConfirmationScreenProps = {
  transcript: string;
  initialItems: readonly VoiceConfirmationItem[];
  isSubmitting?: boolean;
  submitErrorCode?: VoiceConfirmationSubmitErrorCode | null;
  onConfirm: (items: readonly VoiceConfirmationItem[]) => void;
  onCancel: () => void;
  onRecordAgain: () => void;
};

const unitTranslationKeys = {
  kg: "voice.confirmation.units.kg",
  g: "voice.confirmation.units.g",
  l: "voice.confirmation.units.l",
  ml: "voice.confirmation.units.ml",
  packet: "voice.confirmation.units.packet",
  piece: "voice.confirmation.units.piece",
  dozen: "voice.confirmation.units.dozen",
  bottle: "voice.confirmation.units.bottle",
  box: "voice.confirmation.units.box",
  bag: "voice.confirmation.units.bag",
  bunch: "voice.confirmation.units.bunch",
  can: "voice.confirmation.units.can",
  jar: "voice.confirmation.units.jar",
} as const satisfies Record<GroceryUnit, string>;

const submitErrorTranslationKeys = {
  household_unavailable: "voice.confirmation.errors.householdUnavailable",
  network_unavailable: "voice.confirmation.errors.networkUnavailable",
  save_failed: "voice.confirmation.errors.saveFailed",
  session_expired: "voice.confirmation.errors.sessionExpired",
} as const satisfies Record<VoiceConfirmationSubmitErrorCode, string>;

export function VoiceConfirmationScreen({
  transcript,
  initialItems,
  isSubmitting = false,
  submitErrorCode = null,
  onConfirm,
  onCancel,
  onRecordAgain,
}: VoiceConfirmationScreenProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<VoiceConfirmationItem[]>(() =>
    initialItems.map((item) => ({ ...item })),
  );
  const [unitItemId, setUnitItemId] = useState<string | null>(null);
  const errorsById = useMemo(
    () => new Map(items.map((item) => [item.id, validateVoiceConfirmationItem(item)])),
    [items],
  );
  const canConfirm = isVoiceConfirmationValid(items) && !isSubmitting;
  const selectedItem = items.find((item) => item.id === unitItemId) ?? null;

  function updateItem(
    itemId: string,
    changes: Partial<
      Pick<VoiceConfirmationItem, "canonicalKey" | "name" | "quantity" | "unit">
    >,
  ) {
    setItems((currentItems) =>
      currentItems.map((item) => (item.id === itemId ? { ...item, ...changes } : item)),
    );
  }

  function removeItem(itemId: string) {
    setItems((currentItems) => currentItems.filter((item) => item.id !== itemId));
  }

  function confirmItems() {
    if (!canConfirm) {
      return;
    }
    onConfirm(items.map(normalizeVoiceConfirmationItem));
  }

  function selectUnit(unit: GroceryUnit | null) {
    if (unitItemId) {
      updateItem(unitItemId, { unit });
    }
    setUnitItemId(null);
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.screen}
    >
      <View style={styles.header}>
        <Text accessibilityRole="header" style={styles.title}>
          {t("voice.confirmation.title")}
        </Text>
        <Text style={styles.subtitle}>{t("voice.confirmation.subtitle")}</Text>
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.transcriptSection}>
          <Text style={styles.sectionLabel}>{t("voice.confirmation.heardLabel")}</Text>
          <Text selectable style={styles.transcript}>
            {transcript}
          </Text>
        </View>

        <View style={styles.itemsHeader}>
          <Text style={styles.sectionTitle}>{t("voice.confirmation.itemsLabel")}</Text>
          <Text style={styles.itemCount}>
            {t("voice.confirmation.itemCount", { count: items.length })}
          </Text>
        </View>

        {items.length === 0 ? (
          <View accessibilityLiveRegion="polite" style={styles.emptyState}>
            <Ionicons color="#65756C" name="basket-outline" size={28} />
            <Text style={styles.emptyText}>{t("voice.confirmation.empty")}</Text>
          </View>
        ) : null}

        {items.map((item, index) => {
          const errors = errorsById.get(item.id);
          const accessibleItemName =
            normalizeVoiceConfirmationItem(item).name || index + 1;
          const unitLabel = item.unit
            ? t(unitTranslationKeys[item.unit])
            : t("voice.confirmation.noUnit");

          return (
            <View key={item.id} style={styles.itemCard}>
              <View style={styles.itemHeader}>
                <Text style={styles.itemNumber}>{index + 1}</Text>
                <Pressable
                  accessibilityLabel={t("voice.confirmation.removeItem", {
                    name: accessibleItemName,
                  })}
                  accessibilityRole="button"
                  disabled={isSubmitting}
                  hitSlop={8}
                  onPress={() => removeItem(item.id)}
                  style={({ pressed }) => [
                    styles.iconButton,
                    pressed ? styles.pressed : null,
                  ]}
                >
                  <Ionicons color="#A12A22" name="trash-outline" size={20} />
                </Pressable>
              </View>

              <Text style={styles.fieldLabel}>{t("voice.confirmation.itemName")}</Text>
              <TextInput
                accessibilityLabel={t("voice.confirmation.itemNameAccessibility", {
                  number: index + 1,
                })}
                editable={!isSubmitting}
                maxLength={161}
                onChangeText={(name) =>
                  updateItem(item.id, { canonicalKey: null, name })
                }
                style={[styles.input, errors?.name ? styles.inputError : null]}
                value={item.name}
              />
              {errors?.name ? (
                <Text accessibilityRole="alert" style={styles.errorText}>
                  {t(
                    errors.name === "required"
                      ? "voice.confirmation.nameRequired"
                      : "voice.confirmation.nameTooLong",
                  )}
                </Text>
              ) : null}

              <View style={styles.detailRow}>
                <View style={styles.detailField}>
                  <Text style={styles.fieldLabel}>
                    {t("voice.confirmation.quantity")}
                  </Text>
                  <TextInput
                    accessibilityLabel={t("voice.confirmation.quantityAccessibility", {
                      number: index + 1,
                    })}
                    editable={!isSubmitting}
                    inputMode="decimal"
                    maxLength={11}
                    onChangeText={(quantity) => updateItem(item.id, { quantity })}
                    placeholder={t("voice.confirmation.quantityPlaceholder")}
                    style={[styles.input, errors?.quantity ? styles.inputError : null]}
                    value={item.quantity}
                  />
                </View>
                <View style={styles.detailField}>
                  <Text style={styles.fieldLabel}>{t("voice.confirmation.unit")}</Text>
                  <Pressable
                    accessibilityLabel={t("voice.confirmation.unitAccessibility", {
                      name: accessibleItemName,
                      unit: unitLabel,
                    })}
                    accessibilityRole="button"
                    disabled={isSubmitting}
                    onPress={() => setUnitItemId(item.id)}
                    style={({ pressed }) => [
                      styles.unitButton,
                      pressed ? styles.pressed : null,
                    ]}
                  >
                    <Text numberOfLines={1} style={styles.unitButtonText}>
                      {unitLabel}
                    </Text>
                    <Ionicons color="#405249" name="chevron-down" size={18} />
                  </Pressable>
                </View>
              </View>
              {errors?.quantity ? (
                <Text accessibilityRole="alert" style={styles.errorText}>
                  {t(
                    errors.quantity === "required_for_unit"
                      ? "voice.confirmation.quantityRequiredForUnit"
                      : "voice.confirmation.quantityInvalid",
                  )}
                </Text>
              ) : null}
            </View>
          );
        })}
      </ScrollView>

      {submitErrorCode ? (
        <Text accessibilityRole="alert" style={styles.submitError}>
          {t(submitErrorTranslationKeys[submitErrorCode])}
        </Text>
      ) : null}

      <View style={styles.footer}>
        <View style={styles.secondaryActions}>
          <Pressable
            accessibilityRole="button"
            disabled={isSubmitting}
            onPress={onCancel}
            style={({ pressed }) => [
              styles.secondaryButton,
              pressed ? styles.pressed : null,
            ]}
          >
            <Text style={styles.secondaryButtonText}>
              {t("voice.confirmation.cancel")}
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            disabled={isSubmitting}
            onPress={onRecordAgain}
            style={({ pressed }) => [
              styles.secondaryButton,
              pressed ? styles.pressed : null,
            ]}
          >
            <Ionicons color="#33443A" name="mic-outline" size={19} />
            <Text style={styles.secondaryButtonText}>
              {t("voice.confirmation.recordAgain")}
            </Text>
          </Pressable>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: !canConfirm, busy: isSubmitting }}
          disabled={!canConfirm}
          onPress={confirmItems}
          style={({ pressed }) => [
            styles.confirmButton,
            !canConfirm ? styles.disabledButton : null,
            pressed ? styles.pressed : null,
          ]}
        >
          <Ionicons color="#FFFFFF" name="checkmark" size={21} />
          <Text style={styles.confirmButtonText}>
            {isSubmitting
              ? t("voice.confirmation.submitting")
              : t("voice.confirmation.confirm", { count: items.length })}
          </Text>
        </Pressable>
      </View>

      <Modal
        animationType="slide"
        onRequestClose={() => setUnitItemId(null)}
        transparent
        visible={selectedItem !== null}
      >
        <View style={styles.modalOverlay}>
          <Pressable
            accessibilityLabel={t("voice.confirmation.closeUnitMenu")}
            accessibilityRole="button"
            onPress={() => setUnitItemId(null)}
            style={styles.modalDismissArea}
          />
          <View accessibilityViewIsModal style={styles.unitMenu}>
            <View style={styles.unitMenuHeader}>
              <Text accessibilityRole="header" style={styles.unitMenuTitle}>
                {t("voice.confirmation.selectUnit")}
              </Text>
              <Pressable
                accessibilityLabel={t("voice.confirmation.closeUnitMenu")}
                accessibilityRole="button"
                hitSlop={8}
                onPress={() => setUnitItemId(null)}
                style={styles.iconButton}
              >
                <Ionicons color="#33443A" name="close" size={22} />
              </Pressable>
            </View>
            <ScrollView style={styles.unitOptions}>
              {[null, ...GROCERY_UNITS].map((unit) => {
                const label = unit
                  ? t(unitTranslationKeys[unit])
                  : t("voice.confirmation.noUnit");
                const selected = selectedItem?.unit === unit;
                return (
                  <Pressable
                    accessibilityRole="menuitem"
                    key={unit ?? "none"}
                    onPress={() => selectUnit(unit)}
                    style={({ pressed }) => [
                      styles.unitOption,
                      pressed ? styles.pressed : null,
                    ]}
                  >
                    <Text style={styles.unitOptionText}>{label}</Text>
                    {selected ? (
                      <Ionicons color="#176B45" name="checkmark" size={20} />
                    ) : null}
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  confirmButton: {
    alignItems: "center",
    backgroundColor: "#176B45",
    borderRadius: 6,
    flexDirection: "row",
    gap: 8,
    height: 50,
    justifyContent: "center",
    paddingHorizontal: 18,
  },
  confirmButtonText: {
    color: "#FFFFFF",
    flexShrink: 1,
    fontSize: 16,
    fontWeight: "700",
    textAlign: "center",
  },
  detailField: {
    flex: 1,
    minWidth: 120,
  },
  detailRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
  disabledButton: {
    backgroundColor: "#93A29A",
  },
  emptyState: {
    alignItems: "center",
    borderColor: "#C9D3CD",
    borderRadius: 6,
    borderStyle: "dashed",
    borderWidth: 1,
    gap: 8,
    padding: 24,
  },
  emptyText: {
    color: "#52635A",
    fontSize: 15,
    textAlign: "center",
  },
  errorText: {
    color: "#A12A22",
    fontSize: 13,
    lineHeight: 18,
    marginTop: 5,
  },
  fieldLabel: {
    color: "#405249",
    fontSize: 13,
    fontWeight: "700",
    marginBottom: 6,
  },
  footer: {
    backgroundColor: "#FFFFFF",
    borderTopColor: "#DCE4DF",
    borderTopWidth: 1,
    gap: 10,
    padding: 16,
  },
  header: {
    backgroundColor: "#FFFFFF",
    borderBottomColor: "#DCE4DF",
    borderBottomWidth: 1,
    gap: 4,
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  iconButton: {
    alignItems: "center",
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  input: {
    backgroundColor: "#FFFFFF",
    borderColor: "#A8B8AE",
    borderRadius: 6,
    borderWidth: 1,
    color: "#1E3528",
    fontSize: 16,
    height: 46,
    paddingHorizontal: 12,
  },
  inputError: {
    borderColor: "#B42318",
  },
  itemCard: {
    backgroundColor: "#FFFFFF",
    borderColor: "#D5DED8",
    borderRadius: 6,
    borderWidth: 1,
    padding: 14,
  },
  itemCount: {
    color: "#65756C",
    fontSize: 14,
  },
  itemHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  itemNumber: {
    color: "#176B45",
    fontSize: 14,
    fontWeight: "800",
  },
  itemsHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  modalDismissArea: {
    flex: 1,
  },
  modalOverlay: {
    backgroundColor: "rgba(16, 31, 23, 0.42)",
    flex: 1,
    justifyContent: "flex-end",
  },
  pressed: {
    opacity: 0.7,
  },
  screen: {
    backgroundColor: "#F4F7F5",
    flex: 1,
  },
  scrollContent: {
    gap: 14,
    padding: 16,
  },
  secondaryActions: {
    flexDirection: "row",
    gap: 10,
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderColor: "#A8B8AE",
    borderRadius: 6,
    borderWidth: 1,
    flex: 1,
    flexDirection: "row",
    gap: 7,
    height: 46,
    justifyContent: "center",
    paddingHorizontal: 10,
  },
  secondaryButtonText: {
    color: "#33443A",
    flexShrink: 1,
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center",
  },
  sectionLabel: {
    color: "#52635A",
    fontSize: 13,
    fontWeight: "700",
  },
  sectionTitle: {
    color: "#1E3528",
    fontSize: 17,
    fontWeight: "800",
  },
  submitError: {
    backgroundColor: "#FFF2F0",
    color: "#A12A22",
    fontSize: 14,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  subtitle: {
    color: "#52635A",
    fontSize: 14,
    lineHeight: 20,
  },
  title: {
    color: "#173B2A",
    fontSize: 22,
    fontWeight: "800",
  },
  transcript: {
    color: "#1E3528",
    fontSize: 17,
    lineHeight: 25,
  },
  transcriptSection: {
    backgroundColor: "#E8F1EC",
    borderLeftColor: "#2B7A55",
    borderLeftWidth: 3,
    gap: 6,
    padding: 14,
  },
  unitButton: {
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderColor: "#A8B8AE",
    borderRadius: 6,
    borderWidth: 1,
    flexDirection: "row",
    gap: 6,
    height: 46,
    justifyContent: "space-between",
    paddingHorizontal: 12,
  },
  unitButtonText: {
    color: "#1E3528",
    flex: 1,
    fontSize: 15,
  },
  unitMenu: {
    backgroundColor: "#FFFFFF",
    borderTopLeftRadius: 6,
    borderTopRightRadius: 6,
    maxHeight: "72%",
    paddingBottom: 12,
  },
  unitMenuHeader: {
    alignItems: "center",
    borderBottomColor: "#DCE4DF",
    borderBottomWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  unitMenuTitle: {
    color: "#173B2A",
    fontSize: 18,
    fontWeight: "800",
  },
  unitOption: {
    alignItems: "center",
    flexDirection: "row",
    height: 48,
    justifyContent: "space-between",
    paddingHorizontal: 18,
  },
  unitOptionText: {
    color: "#263D31",
    fontSize: 16,
  },
  unitOptions: {
    flexGrow: 0,
  },
});
