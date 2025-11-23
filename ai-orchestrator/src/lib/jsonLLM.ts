import { logRawLLM } from "./logger";

interface ParseOptions<T> {
  purpose: string;
  onErrorFallback?: () => T;
}

export async function parseLLMJson<T = any>(
  raw: string,
  options: ParseOptions<T>
): Promise<T | null> {
  await logRawLLM(options.purpose, raw);

  if (!raw || typeof raw !== "string") {
    return options.onErrorFallback ? options.onErrorFallback() : null;
  }

  const firstBrace = raw.indexOf("{");
  const lastBrace = raw.lastIndexOf("}");

  let candidate = raw;
  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    candidate = raw.slice(firstBrace, lastBrace + 1);
  }

  try {
    return JSON.parse(candidate);
  } catch {
    return options.onErrorFallback ? options.onErrorFallback() : null;
  }
}
