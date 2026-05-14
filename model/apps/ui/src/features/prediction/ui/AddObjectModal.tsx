import { useEffect, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { predictObject } from "../api/predictionApi";
import { PredictionResponse, PredictObjectInput } from "../model/types";
import { isApiError } from "../../../shared/api/client";
import { useLanguage } from "../../../shared/i18n/LanguageContext";
import { AddObjectForm } from "./AddObjectForm";
import { PredictionResult } from "./PredictionResult";
import styles from "./AddObjectModal.module.css";

type AddObjectModalProps = {
  open: boolean;
  onClose: () => void;
};

export function AddObjectModal({ open, onClose }: AddObjectModalProps) {
  const queryClient = useQueryClient();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const { t } = useLanguage();

  const mutation = useMutation<PredictionResponse, unknown, PredictObjectInput>({
    mutationFn: predictObject,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      void queryClient.invalidateQueries({ queryKey: ["shortlist"] });
    },
  });

  useEffect(() => {
    if (!open) {
      mutation.reset();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const submitError = mutation.isError
    ? isApiError(mutation.error)
      ? mutation.error.message
      : t("addObject.errors.predictionFailed")
    : null;

  return (
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className={styles.dialog}
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-object-modal-title"
      >
        <header className={styles.header}>
          <div>
            <p className={styles.kicker}>{t("addObject.modal.kicker")}</p>
            <h2 id="add-object-modal-title" className={styles.title}>
              {t("addObject.modal.title")}
            </h2>
          </div>
          <button
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label={t("addObject.modal.close")}
          >
            ×
          </button>
        </header>

        <div className={styles.body}>
          {mutation.data ? (
            <>
              <PredictionResult result={mutation.data} />
              <div className={styles.postActions}>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={() => mutation.reset()}
                >
                  {t("addObject.actions.scoreAnother")}
                </button>
                <button
                  type="button"
                  className={styles.primaryButton}
                  onClick={onClose}
                >
                  {t("addObject.actions.done")}
                </button>
              </div>
            </>
          ) : (
            <AddObjectForm
              onSubmit={(input) => mutation.mutate(input)}
              onCancel={onClose}
              isPending={mutation.isPending}
              submitError={submitError}
            />
          )}
        </div>
      </div>
    </div>
  );
}
