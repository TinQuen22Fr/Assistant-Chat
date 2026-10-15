import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiFetch, apiJson } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // null = vérification en cours, false = non connecté, objet = utilisateur
  const [user, setUser] = useState(null);

  const check = useCallback(async () => {
    try {
      setUser(await apiJson("/auth/me"));
    } catch {
      setUser(false);
    }
  }, []);

  useEffect(() => {
    // Retour OAuth : AuthCallback se charge de l'échange du session_id
    if (window.location.hash.includes("session_id=")) return;
    check();
  }, [check]);

  const login = async (email, password) =>
    setUser(await apiJson("/auth/login", { method: "POST", body: { email, password } }));

  const register = async (name, email, password) =>
    setUser(await apiJson("/auth/register", { method: "POST", body: { name, email, password } }));

  const logout = async () => {
    await apiFetch("/auth/logout", { method: "POST" });
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, setUser, login, register, logout }}>{children}</AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
