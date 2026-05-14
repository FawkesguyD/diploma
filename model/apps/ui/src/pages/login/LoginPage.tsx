import { Navigate } from "react-router-dom";

import { LoginForm } from "../../features/auth/ui/LoginForm";
import { useCurrentUser } from "../../features/auth/model/useCurrentUser";
import { useLanguage } from "../../shared/i18n/LanguageContext";
import { LanguageSwitcher } from "../../shared/i18n/LanguageSwitcher";
import { StatusCard } from "../../shared/ui/StatusCard";
import styles from "./LoginPage.module.css";

export function LoginPage() {
  const currentUserQuery = useCurrentUser();
  const { t } = useLanguage();

  if (currentUserQuery.isLoading) {
    return <StatusCard title={t("auth.checkingTitle")} description={t("auth.checkingDescription")} />;
  }

  if (currentUserQuery.isError) {
    return (
      <StatusCard
        tone="error"
        title={t("auth.unavailableTitle")}
        description={t("auth.unavailableDescription")}
      />
    );
  }

  if (currentUserQuery.data) {
    return <Navigate to="/shortlist" replace />;
  }

  return (
    <div className={styles.page}>
      <div className={styles.languageSwitch}>
        <LanguageSwitcher />
      </div>
      <section className={styles.panel}>
        <p className={styles.kicker}>{t("auth.loginKicker")}</p>
        <h1 className={styles.title}>{t("auth.loginTitle")}</h1>
        <p className={styles.description}>{t("auth.loginDescription")}</p>
        <LoginForm />
      </section>
    </div>
  );
}
