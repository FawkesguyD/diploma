# UI Module

React/Vite MVP client for the investor shortlist workflow.

## Local run

```bash
cd apps/ui
npm install
npm run dev
```

The dev server proxies `/api/*` to `http://localhost:8000` by default.

## Localization

The UI uses a lightweight in-app localization layer without external i18n dependencies.

- Translation dictionaries live in `src/shared/i18n/translations.ts`.
- The language provider and `t(key)` hook live in `src/shared/i18n/LanguageContext.tsx`.
- Add a new key by adding it to the English dictionary first, then adding the same key to the Russian dictionary.
- Add a new language by extending the `Language` type and adding another dictionary to `translations`.
- The RU / EN switcher is `src/shared/i18n/LanguageSwitcher.tsx`; it is shown in the top user panel and on the login page.
- The default language is Russian.
- The selected language is stored in `localStorage` under `real-estate-ui-language-v2`.
