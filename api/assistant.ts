// api/assistant.ts
export const config = {
  runtime: "edge", // Edge Function for low-latency + streaming
};

type Message = { role: "system" | "user" | "assistant"; content: any };

export default async function handler(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: corsHeaders(),
    });
  }

  if (req.method !== "POST") {
    return json({ error: "Method Not Allowed" }, 405);
  }

  try {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) return json({ error: "Missing OPENAI_API_KEY" }, 500);

    const body = await safeJson(req);
    const { messages, tools, toolChoice, metadata } = body ?? {};

    if (!Array.isArray(messages) || messages.length === 0) {
      return json({ error: "Invalid payload: `messages` required" }, 400);
    }

    // Build OpenAI request
    const payload = {
      model: process.env.OPENAI_MODEL ?? "o4-mini",
      input: messages as Message[],
      // optional tools
      tools,
      tool_choice: toolChoice ?? "auto",
      metadata: { app: "MortgageCRM", ...metadata },
      stream: true,
    };

    // Call OpenAI Responses API (Edge-compatible fetch)
    const openaiResp = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(payload),
    });

    if (!openaiResp.ok || !openaiResp.body) {
      const txt = await openaiResp.text().catch(() => "");
      return json(
        { error: `OpenAI HTTP ${openaiResp.status}: ${txt || openaiResp.statusText}` },
        500
      );
    }

    // Pass-through streaming
    const headers = new Headers({
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      ...corsHeaders(),
    });

    return new Response(openaiResp.body, { status: 200, headers });
  } catch (err: any) {
    return json({ error: err?.message || "Unknown server error" }, 500);
  }
}

/* ---------- utils ---------- */
function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*", // lock down to your domain in prod if desired
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };
}

async function safeJson(req: Request) {
  try {
    return await req.json();
  } catch {
    return undefined;
  }
}

function json(obj: any, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders(),
    },
  });
}
