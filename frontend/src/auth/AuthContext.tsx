import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, setSessionExpiredHandler } from "../api/client";

export interface Me {
  id: number;
  username: string;
  full_name: string;
  email: string;
  must_change_password: boolean;
  mfa_enabled: boolean;
  is_superuser: boolean;
  permissions: string[];
  scopes: Record<string, string[]>;
  roles: string[];
  employee: null | {
    id: number;
    staff_number: string;
    full_name: string;
    department: string | null;
    job_title: string | null;
    photo: string | null;
    is_manager: boolean;
  };
  organization: null | { id: number; name: string; code: string; currency: string; features: string[]; session_timeout_minutes: number };
}

interface AuthState {
  me: Me | null;
  loading: boolean;
  setMe: (m: Me | null) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  can: (perm: string | string[], minScope?: string) => boolean;
  feature: (code: string) => boolean;
}

const Ctx = createContext<AuthState | null>(null);
const SCOPE_RANK: Record<string, number> = { own: 0, team: 1, department: 2, branch: 3, organization: 4 };

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get<Me>("/auth/me/");
      setMe(data);
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout/");
    } finally {
      setMe(null);
      qc.clear();
    }
  }, [qc]);

  useEffect(() => {
    api.get("/auth/csrf/").finally(refresh);
    setSessionExpiredHandler(() => {
      setMe(null);
      qc.clear();
    });
  }, [refresh, qc]);

  // inactivity timeout (session control)
  const timer = useRef<number>();
  useEffect(() => {
    if (!me) return;
    const minutes = me.organization?.session_timeout_minutes || 30;
    const reset = () => {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => logout(), minutes * 60 * 1000);
    };
    const events = ["mousemove", "keydown", "click", "touchstart"];
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => {
      window.clearTimeout(timer.current);
      events.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [me, logout]);

  const value = useMemo<AuthState>(() => ({
    me, loading, setMe, refresh, logout,
    can: (perm, minScope) => {
      if (!me) return false;
      if (me.is_superuser) return true;
      const list = Array.isArray(perm) ? perm : [perm];
      return list.some((p) => {
        if (!me.permissions.includes(p)) return false;
        if (!minScope) return true;
        return (me.scopes[p] || []).some((s) => SCOPE_RANK[s] >= SCOPE_RANK[minScope]);
      });
    },
    feature: (code) => !!me?.organization?.features.includes(code),
  }), [me, loading, refresh, logout]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
