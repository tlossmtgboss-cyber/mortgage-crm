import express from "express";

const app = express();
const PORT = process.env.PORT || 3000;

app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "ai-orchestrator-minimal" });
});

app.listen(Number(PORT), "0.0.0.0", () => {
  console.log(`Minimal server running on port ${PORT}`);
});
