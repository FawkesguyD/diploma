import { Link } from "react-router-dom";

import { useLanguage } from "../../shared/i18n/LanguageContext";
import styles from "./NotFoundPage.module.css";

export function NotFoundPage() {
  const { t } = useLanguage();

  return (
    <div className={styles.page}>
      <section className={styles.card}>
        <h1>{t("notFound.title")}</h1>
        <p>{t("notFound.description")}</p>
        <Link className={styles.link} to="/shortlist">
          {t("notFound.return")}
        </Link>
      </section>
    </div>
  );
}
