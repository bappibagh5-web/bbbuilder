"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authApi, type AuthUser } from "@/lib/auth";

type AuthContextValue = {
  status: "loading" | "authenticated" | "unauthenticated";
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);

  const becomeUnauthenticated = useCallback(() => {
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  useEffect(() => {
    let active = true;
    authApi
      .me()
      .then(({ user: currentUser }) => {
        if (active) {
          setUser(currentUser);
          setStatus("authenticated");
        }
      })
      .catch(() => active && becomeUnauthenticated());
    window.addEventListener("bb-auth-unauthorized", becomeUnauthenticated);
    return () => {
      active = false;
      window.removeEventListener("bb-auth-unauthorized", becomeUnauthenticated);
    };
  }, [becomeUnauthenticated]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      async login(email, password) {
        const response = await authApi.login(email, password);
        setUser(response.user);
        setStatus("authenticated");
      },
      async logout() {
        try {
          await authApi.logout();
        } finally {
          becomeUnauthenticated();
        }
      },
    }),
    [becomeUnauthenticated, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
