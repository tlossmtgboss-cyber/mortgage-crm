export async function logRawLLM(purpose: string, raw: string): Promise<void> {
  console.log("[LLM_RAW]", purpose, raw.slice(0, 1000));
}

export async function logInteraction(payload: any): Promise<void> {
  console.log("[AI_INTERACTION]", JSON.stringify(payload, null, 2));
}
