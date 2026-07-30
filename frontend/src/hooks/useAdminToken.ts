import { useEffect, useState } from "react";

const STORAGE_KEY = "residency-tracker.admin-token";

export function useAdminToken(): [string, (next: string) => void] {
  const [token, setToken] = useState<string>(() => localStorage.getItem(STORAGE_KEY) ?? "");

  useEffect(() => {
    if (token) localStorage.setItem(STORAGE_KEY, token);
    else localStorage.removeItem(STORAGE_KEY);
  }, [token]);

  return [token, setToken];
}
