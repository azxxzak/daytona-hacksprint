export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d
        .map((x) => (x && typeof x === "object" && "msg" in x ? String((x as { msg: unknown }).msg) : ""))
        .filter(Boolean)
        .join(" ") || fallback;
    }
  }
  return fallback;
}

function toLogin() {
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.replace("/login");
  }
}

/** JSON request. A 401 anywhere (except the login call itself) sends the user to /login. */
export async function api<T>(
  path: string,
  init: Omit<RequestInit, "body"> & { json?: unknown; noRedirect?: boolean } = {},
): Promise<T> {
  const { json, noRedirect, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(path, {
      ...rest,
      credentials: "same-origin",
      headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: json !== undefined ? JSON.stringify(json) : undefined,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "network");
  }
  if (res.status === 401 && !noRedirect) toLogin();
  if (res.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) throw new ApiError(res.status, detailOf(body, res.statusText || "error"));
  return body as T;
}

/** Multipart upload through XHR so we can report progress. */
export function uploadTest(
  form: FormData,
  onProgress: (pct: number) => void,
): { promise: Promise<{ id: string }>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<{ id: string }>((resolve, reject) => {
    xhr.open("POST", "/api/tests");
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError(0, "network"));
    xhr.onabort = () => reject(new DOMException("aborted", "AbortError"));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status === 401) toLogin();
      if (xhr.status >= 200 && xhr.status < 300 && body && typeof body === "object" && "id" in body) {
        resolve(body as { id: string });
      } else {
        reject(new ApiError(xhr.status, detailOf(body, xhr.statusText || "error")));
      }
    };
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}
