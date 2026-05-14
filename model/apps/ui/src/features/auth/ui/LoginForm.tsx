import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, isApiError } from "../../../shared/api/client";
import { useLanguage } from "../../../shared/i18n/LanguageContext";
import { login } from "../api/authApi";
import { CURRENT_USER_QUERY_KEY } from "../model/types";
import styles from "./LoginForm.module.css";

export function LoginForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useLanguage();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: async (user) => {
      queryClient.setQueryData(CURRENT_USER_QUERY_KEY, user);
      await queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY });
      navigate("/shortlist", { replace: true });
    },
    onError: (error) => {
      if (isApiError(error)) {
        setFormError(error.message);
        return;
      }
      if (error instanceof ApiError) {
        setFormError(error.message);
        return;
      }
      setFormError(t("auth.loginError"));
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    loginMutation.mutate({
      email: email.trim(),
      password,
    });
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <label className={styles.field}>
        <span className={styles.label}>{t("auth.email")}</span>
        <input
          className={styles.input}
          autoComplete="email"
          name="email"
          onChange={(event) => setEmail(event.target.value)}
          placeholder="investor@example.com"
          type="email"
          value={email}
          required
        />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>{t("auth.password")}</span>
        <input
          className={styles.input}
          autoComplete="current-password"
          name="password"
          onChange={(event) => setPassword(event.target.value)}
          placeholder={t("auth.passwordPlaceholder")}
          type="password"
          value={password}
          required
        />
      </label>

      {formError ? <p className={styles.error}>{formError}</p> : null}

      <button className={styles.submitButton} disabled={loginMutation.isPending} type="submit">
        {loginMutation.isPending ? t("auth.signingIn") : t("auth.login")}
      </button>
    </form>
  );
}
