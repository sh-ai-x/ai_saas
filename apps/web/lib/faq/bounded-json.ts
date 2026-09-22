/** Limit bytes while streaming, including bodies with no Content-Length. */
export async function boundedJson(body: ReadableStream<Uint8Array> | null, maxBytes: number, signal?: AbortSignal): Promise<unknown> {
  if (!body) throw new Error('Missing body');
  const reader = body.getReader();
  const cancel = () => { void reader.cancel().catch(() => {}); };
  signal?.addEventListener('abort', cancel, { once: true });
  const decoder = new TextDecoder();
  let size = 0;
  let text = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (signal?.aborted) throw new Error('Body timeout');
      if (done) break;
      size += value.byteLength;
      if (size > maxBytes) throw new Error('Body too large');
      text += decoder.decode(value, { stream: true });
    }
    return JSON.parse(text + decoder.decode());
  } finally { signal?.removeEventListener('abort', cancel); cancel(); }
}
