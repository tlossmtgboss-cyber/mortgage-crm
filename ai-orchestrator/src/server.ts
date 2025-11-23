import * as dotenv from "dotenv";
dotenv.config();

import express from "express";
import cors from "cors";
import { processMessage, UserMessage } from "./ai/orchestrator/smartAssistant";

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json());

// Health check
app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "ai-orchestrator" });
});

// Main AI endpoint
app.post("/api/v1/ai/smart-assistant", async (req, res) => {
  try {
    const { userId, sessionId, text, channel, metadata } = req.body;

    if (!text) {
      return res.status(400).json({ error: "Missing required field: text" });
    }

    const message: UserMessage = {
      userId: userId || "anonymous",
      sessionId: sessionId || `session-${Date.now()}`,
      text,
      channel: channel || "web",
      metadata: {
        ...metadata,
        authToken: req.headers.authorization?.replace("Bearer ", "") || metadata?.authToken
      }
    };

    const result = await processMessage(message);

    res.json({
      success: true,
      answer: result.answer,
      confidence: result.confidence,
      escalationRequired: result.escalationRequired,
      escalationReason: result.escalationReason,
      actionsExecuted: result.actionsExecuted,
      meta: result.meta
    });
  } catch (error) {
    console.error("[ERROR] Smart assistant failed:", error);
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : "Internal server error"
    });
  }
});

// Start server
app.listen(Number(PORT), "0.0.0.0", () => {
  console.log(`🤖 AI Orchestrator running on port ${PORT}`);
  console.log(`   Health: http://0.0.0.0:${PORT}/health`);
  console.log(`   API: POST http://0.0.0.0:${PORT}/api/v1/ai/smart-assistant`);
});
