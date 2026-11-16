import { ApiError } from "./api";
import type { Key } from "./i18n";

export function errorText(e: unknown, t: (k: Key) => string): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return t("err.network");
    if (e.status === 413) return t("err.tooLarge");
    if (e.status === 404) return t("err.notFound");
    if (e.status >= 500) return t("err.generic");
    return e.message;
  }
  return t("err.generic");
}
