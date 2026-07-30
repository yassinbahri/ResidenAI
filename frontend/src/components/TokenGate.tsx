import { FormEvent, useState } from "react";
import { ApiError, getProviders } from "../lib/api";

export function TokenGate({ onConnected }: { onConnected: (token: string) => void }) {
  const [value, setValue] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setChecking(true);
    setError(null);
    try {
      await getProviders(value);
      onConnected(value);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Invalid admin token." : "Could not reach the tracker API.");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="token-gate">
      <form className="token-gate-form" onSubmit={handleSubmit}>
        <h1>Residency Tracker</h1>
        <p className="token-gate-hint">Internal only. Enter the admin token to continue.</p>
        <label>
          Admin token
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
            required
          />
        </label>
        <button type="submit" disabled={checking}>
          {checking ? "Checking…" : "Connect"}
        </button>
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
      </form>
    </div>
  );
}
