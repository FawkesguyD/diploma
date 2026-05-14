import { PropsWithChildren } from "react";
import { Navigate } from "react-router-dom";

import { useLanguage } from "../../../shared/i18n/LanguageContext";
import { StatusCard } from "../../../shared/ui/StatusCard";
import { getReadableAuthError, useCurrentUser } from "../model/useCurrentUser";

export function AuthGuard({ children }: PropsWithChildren) {
  const currentUserQuery = useCurrentUser();
  const { t } = useLanguage();

  if (currentUserQuery.isLoading) {
    return <StatusCard title={t("auth.checkingTitle")} description={t("auth.restoringDescription")} />;
  }

  if (currentUserQuery.isError) {
    return (
      <StatusCard
        tone="error"
        title={t("auth.sessionFailedTitle")}
        description={getReadableAuthError(
          currentUserQuery.error,
          t("auth.checkFailedDescription"),
        )}
      />
    );
  }

  if (!currentUserQuery.data) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
