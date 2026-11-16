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
  init: Omit<RequestInit, "body"> & { json?: unknown; form?: FormData; noRedirect?: boolean } = {},
): Promise<T> {
  const { json, form, noRedirect, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(path, {
      ...rest,
      credentials: "same-origin",
      headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: form ?? (json !== undefined ? JSON.stringify(json) : undefined),
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

export type AskEvent =
  | { event: "user"; data: { content: string; at: string } }
  | { event: "thinking"; data: { persona_id: string } }
  | { event: "message"; data: { persona_id: string; content: string; at: string } }
  | { event: "suggestion"; data: { content: string | null } }
  | { event: "done"; data: Record<string, never> }
  | { event: "error"; data: { detail?: string } };

/** POST that answers with text/event-stream; calls onEvent for each parsed event. */
export async function streamAsk(
  path: string,
  body: { message: string } | { use_suggestion: true },
  onEvent: (e: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "network");
  }
  if (res.status === 401) toLogin();
  if (!res.ok || !res.body) {
    let b: unknown = null;
    try {
      b = await res.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detailOf(b, res.statusText || "error"));
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  const flush = (block: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (!data.length) return;
    try {
      onEvent({ event, data: JSON.parse(data.join("\n")) } as AskEvent);
    } catch {
      /* malformed event, skip */
    }
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.search(/\r?\n\r?\n/)) >= 0) {
      const m = buf.slice(i).match(/^\r?\n\r?\n/)!;
      flush(buf.slice(0, i));
      buf = buf.slice(i + m[0].length);
    }
  }
  if (buf.trim()) flush(buf);
}
