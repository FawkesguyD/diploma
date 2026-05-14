export type AuthUser = {
  id: number;
  name: string;
  email: string;
};

export type LoginInput = {
  email: string;
  password: string;
};

export const CURRENT_USER_QUERY_KEY = ["auth", "me"] as const;
