import { useEffect, useState } from "react";
import { ApiError, getMe } from "@/lib/api";

type AuthState =
  | { status: "loading" }
  | { status: "signed-in"; email: string; logoutUrl: string | null }
  | { status: "unauthenticated" }
  | { status: "error"; message: string };

/** Resolves the current user once on mount via `GET /api/me`.
 *
 * 401 → `unauthenticated` (Cloudflare Access hasn't stamped a header, or the
 * local dev env var is unset). Any other error → `error`. */
export function useAuth(): AuthState {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then(({ email, logout_url }) => {
        if (!cancelled)
          setState({ status: "signed-in", email, logoutUrl: logout_url });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 401) {
          setState({ status: "unauthenticated" });
        } else {
          setState({
            status: "error",
            message: e instanceof Error ? e.message : String(e),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
