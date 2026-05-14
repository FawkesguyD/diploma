import { useLanguage } from "./LanguageContext";
import styles from "./LanguageSwitcher.module.css";

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();

  return (
    <div className={styles.switcher} aria-label={t("app.language.label")}>
      <button
        className={language === "ru" ? styles.activeButton : styles.button}
        onClick={() => setLanguage("ru")}
        type="button"
      >
        {t("app.language.russian")}
      </button>
      <button
        className={language === "en" ? styles.activeButton : styles.button}
        onClick={() => setLanguage("en")}
        type="button"
      >
        {t("app.language.english")}
      </button>
    </div>
  );
}
