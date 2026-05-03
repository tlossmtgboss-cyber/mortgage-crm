import OpenAI from "openai";

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  timeout: 30_000,
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
  const providerModel = selectProviderModel(options.modelName);

  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [];

  if (options.systemPrompt) {
    messages.push({ role: "system", content: options.systemPrompt });
  }
  messages.push({ role: "user", content: prompt });

  const response = await openai.chat.completions.create({
    model: providerModel,
    messages,
    temperature: options.temperature ?? 0.1,
    max_tokens: options.maxTokens ?? 512,
    response_format: options.json ? { type: "json_object" } : undefined
  });

  return response.choices[0].message.content ?? "";
}
