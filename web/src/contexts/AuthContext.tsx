import { createContext, useContext, useState, useEffect, useCallback } from "react";
import {
  eAuth,
  getToken,
  setToken,
  clearToken,
  setRefreshToken,
  setTokenExpiry,
} from "@/lib/enterpriseApi";
import type { UserProfile } from "@/lib/enterpriseApi";

interface AuthState {
  user: UserProfile | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, username?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setTokenState] = useState<string | null>(getToken);
  const [isLoading, setIsLoading] = useState(true);

  // On mount, validate the stored token
  useEffect(() => {
    if (!token) { setIsLoading(false); return; }
    eAuth.me()
      .then(setUser)
      .catch(() => { clearToken(); setTokenState(null); })
      .finally(() => setIsLoading(false));
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const _saveTokens = useCallback((access: string, refresh: string) => {
    setToken(access);
    setRefreshToken(refresh);
    setTokenExpiry(60); // ACCESS_TOKEN_EXPIRE_MINUTES = 60
    setTokenState(access);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await eAuth.login(email, password);
    _saveTokens(tokens.access_token, tokens.refresh_token);
    const profile = await eAuth.me();
    setUser(profile);
  }, [_saveTokens]);

  const register = useCallback(async (email: string, password: string, username?: string) => {
    const tokens = await eAuth.register(email, password, username);
    _saveTokens(tokens.access_token, tokens.refresh_token);
    const profile = await eAuth.me();
    setUser(profile);
  }, [_saveTokens]);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{
      user, token, isAuthenticated: !!user, isLoading,
      login, register, logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
