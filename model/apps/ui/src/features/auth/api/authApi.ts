import { apiFetch } from "../../../shared/api/client";
import { AuthUser, LoginInput } from "../model/types";

export function login(payload: LoginInput) {
  return apiFetch<AuthUser>("/auth/login", {
    method: "POST",
    json: payload,
  });
}

export function logout() {
  return apiFetch<{ status: string }>("/auth/logout", {
    method: "POST",
  });
}

export function getCurrentUser() {
  return apiFetch<AuthUser>("/auth/me");
}
