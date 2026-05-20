import OpenAI from "openai";

const apiKey = process.env.OPENAI_API_KEY;
if (!apiKey) {
  console.error("[LLM] WARNING: OPENAI_API_KEY not set — all LLM calls will fail");
}

const openai = new OpenAI({
  apiKey: apiKey || "missing-key",
  timeout: 30000,
  maxRetries: 2,
});

export interface LLMOptions {
  systemPrompt?: string;
  temperature?: number;
  maxTokens?: number;
  json?: boolean;
  modelName?: string;
}

function selectProviderModel(modelName?: string): string {
  switch (modelName) {
    case "router":
      return "gpt-4o-mini";
    case "evaluator":
      return "gpt-4o-mini";
    case "advisor":
      return "gpt-4o";
    case "compliance":
      return "gpt-4o";
    default:
      return "gpt-4o-mini";
  }
}

export async function callLLM(
  prompt: string,
  options: LLMOptions = {}
): Promise<string> {
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY not configured");
  }

  const providerModel = selectProviderModel(options.modelName);

  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [];

  if (options.systemPrompt) {
    messages.push({ role: "system", content: options.systemPrompt });
  }
  messages.push({ role: "user", content: prompt });

  try {
    const response = await openai.chat.completions.create({
      model: providerModel,
      messages,
      temperature: options.temperature ?? 0.1,
      max_tokens: options.maxTokens ?? 512,
      response_format: options.json ? { type: "json_object" } : undefined
    });

    return response.choices[0].message.content ?? "";
  } catch (error: any) {
    console.error(`[LLM] ${providerModel} call failed: ${error.message}`);
    throw error;
  }
}
