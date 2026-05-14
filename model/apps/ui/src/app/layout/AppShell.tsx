import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PropsWithChildren } from "react";
import { useNavigate } from "react-router-dom";

import { logout } from "../../features/auth/api/authApi";
import { AuthUser, CURRENT_USER_QUERY_KEY } from "../../features/auth/model/types";
import { useLanguage } from "../../shared/i18n/LanguageContext";
import { LanguageSwitcher } from "../../shared/i18n/LanguageSwitcher";
import styles from "./AppShell.module.css";

type AppShellProps = PropsWithChildren<{
  user: AuthUser;
}>;

export function AppShell({ user, children }: AppShellProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useLanguage();
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      queryClient.setQueryData(CURRENT_USER_QUERY_KEY, null);
      await queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY });
      navigate("/login", { replace: true });
    },
  });

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>{t("app.eyebrow")}</p>
          <h1 className={styles.title}>{t("app.title")}</h1>
        </div>
        <div className={styles.userPanel}>
          <LanguageSwitcher />
          <div className={styles.userMeta}>
            <span className={styles.userName}>{user.name}</span>
            <span className={styles.userEmail}>{user.email}</span>
          </div>
          <button
            className={styles.logoutButton}
            onClick={() => logoutMutation.mutate()}
            disabled={logoutMutation.isPending}
            type="button"
          >
            {logoutMutation.isPending ? t("app.signingOut") : t("app.logout")}
          </button>
        </div>
      </header>
      <main className={styles.content}>{children}</main>
    </div>
  );
}
