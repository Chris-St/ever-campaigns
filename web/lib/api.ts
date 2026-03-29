const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type RequestOptions = Omit<RequestInit, "body"> & {
  token?: string | null;
  body?: unknown;
};

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { token, headers, body, ...rest } = options;
  const isFormData = body instanceof FormData;
  const serializedBody =
    body == null
      ? undefined
      : typeof body === "string" ||
          body instanceof FormData ||
          body instanceof Blob ||
          body instanceof URLSearchParams ||
          body instanceof ArrayBuffer ||
          ArrayBuffer.isView(body)
        ? body
        : JSON.stringify(body);

  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      ...(!isFormData ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: serializedBody as BodyInit | undefined,
    cache: "no-store",
  });

  if (!response.ok) {
    const fallbackMessage = `Request failed with ${response.status}`;
    let message = fallbackMessage;
    try {
      const errorPayload = (await response.json()) as { detail?: string };
      message = errorPayload.detail ?? fallbackMessage;
    } catch {
      message = fallbackMessage;
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
