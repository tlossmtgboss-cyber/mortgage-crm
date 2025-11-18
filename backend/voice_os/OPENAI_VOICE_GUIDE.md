# OpenAI Voice Configuration Guide

## Overview

Your Voice OS is now configured to use **OpenAI for everything**:
- ✅ **Speech-to-Text**: OpenAI Whisper API
- ✅ **Text-to-Speech**: OpenAI TTS API
- ✅ **LLM**: OpenAI GPT-4o/GPT-3.5

**Benefits:**
- Just 2 API keys needed (Twilio + OpenAI)
- Simple billing (one invoice for voice services)
- 6 different voices to choose from
- Lower cost at scale

---

## Available Voices

OpenAI TTS provides 6 natural-sounding voices:

### 1. **alloy** (Default)
- **Description**: Neutral and balanced
- **Best for**: General purpose, professional settings
- **Tone**: Clear, versatile, neither distinctly male nor female
- **Recommended for**: Business calls, receptionist

### 2. **echo**
- **Description**: Clear and professional
- **Best for**: Corporate environments
- **Tone**: Authoritative, crisp
- **Recommended for**: Professional services, formal communications

### 3. **fable**
- **Description**: Warm and expressive
- **Best for**: Customer service, friendly interactions
- **Tone**: Engaging, personable, upbeat
- **Recommended for**: Sales calls, customer support

### 4. **onyx**
- **Description**: Deep and authoritative
- **Best for**: Serious or formal contexts
- **Tone**: Masculine, commanding, trustworthy
- **Recommended for**: Executive calls, financial services

### 5. **nova**
- **Description**: Energetic and friendly
- **Best for**: Casual, upbeat interactions
- **Tone**: Youthful, enthusiastic
- **Recommended for**: Marketing, customer engagement

### 6. **shimmer**
- **Description**: Soft and gentle
- **Best for**: Calm, soothing interactions
- **Tone**: Feminine, warm, reassuring
- **Recommended for**: Healthcare, counseling, support lines

---

## How to Configure

### Option 1: Environment Variable (Recommended)

Set the default voice for all calls in `.env`:

```bash
TTS_VOICE=alloy
```

Change to any voice:
```bash
TTS_VOICE=echo      # Professional
TTS_VOICE=fable     # Warm and friendly
TTS_VOICE=onyx      # Deep and authoritative
TTS_VOICE=nova      # Energetic
TTS_VOICE=shimmer   # Soft and gentle
```

### Option 2: Per-Agent Configuration

Configure different voices for different use cases in your CRM agent settings:

```json
{
  "agent_id": "receptionist-1",
  "name": "AI Receptionist",
  "voice_id": "alloy",
  "voice_config": {
    "stt_provider": "openai",
    "tts_provider": "openai"
  }
}
```

Example configurations:

**Receptionist/General Inquiries:**
```json
{ "voice_id": "alloy" }
```

**Sales Calls:**
```json
{ "voice_id": "fable" }
```

**Executive/Loan Officer:**
```json
{ "voice_id": "onyx" }
```

**Customer Support:**
```json
{ "voice_id": "nova" }
```

---

## Testing Different Voices

### Quick Test Script

```bash
# Update .env with different voice
export TTS_VOICE=fable

# Restart server
npm run dev

# Make a test call to hear the new voice
```

### A/B Testing

Test multiple voices to find what works best for your brand:

1. Create multiple test agents with different voices
2. Route calls to different agents
3. Track customer feedback
4. Measure engagement metrics

```bash
# Agent 1 - Alloy (neutral)
curl -X POST http://localhost:8080/api/agents \
  -d '{"name":"Test 1","voice_id":"alloy"}'

# Agent 2 - Fable (warm)
curl -X POST http://localhost:8080/api/agents \
  -d '{"name":"Test 2","voice_id":"fable"}'

# Agent 3 - Onyx (authoritative)
curl -X POST http://localhost:8080/api/agents \
  -d '{"name":"Test 3","voice_id":"onyx"}'
```

---

## Voice Quality Settings

### Standard Quality (Recommended)

```bash
# In .env
OPENAI_TTS_MODEL=tts-1
```

**Specs:**
- Cost: $15 per 1M characters
- Latency: ~300-500ms
- Quality: High quality, suitable for most use cases

### HD Quality (Premium)

```bash
# In .env
OPENAI_TTS_MODEL=tts-1-hd
```

**Specs:**
- Cost: $30 per 1M characters (2x standard)
- Latency: ~500-800ms
- Quality: Premium fidelity, best for critical calls

**When to use HD:**
- High-value client interactions
- Executive communications
- Marketing presentations
- When audio quality is paramount

---

## Speech Speed Control

Adjust speaking speed for different scenarios:

```bash
# Normal speed (default)
OPENAI_TTS_SPEED=1.0

# Slower (better comprehension)
OPENAI_TTS_SPEED=0.9

# Faster (more energetic)
OPENAI_TTS_SPEED=1.1
```

**Recommended speeds by use case:**
- **0.9**: Complex information, elderly callers, legal/medical
- **1.0**: Standard business calls (default)
- **1.1**: Sales, marketing, energetic interactions

---

## Cost Optimization

### Cost Per Minute by Voice Quality

**Standard (tts-1):**
- 150 words/minute = ~900 characters
- Cost: $0.0135 per minute
- 1000 hours: ~$810/month

**HD (tts-1-hd):**
- 150 words/minute = ~900 characters
- Cost: $0.027 per minute
- 1000 hours: ~$1,620/month

### Optimization Tips

1. **Use Standard for Most Calls**
   ```bash
   OPENAI_TTS_MODEL=tts-1
   ```

2. **Cache Common Phrases**
   - Pre-generate frequently used responses
   - Store in CDN or local cache
   - Save 60-80% on TTS costs

3. **Smart Routing**
   - Use HD for VIP clients only
   - Standard for general inquiries
   - Configure per-agent

---

## Integration with Your CRM

### Update Vapi Agent to Voice OS

Your current Vapi setup uses PlayHT. Here's how to migrate:

**Before (Vapi):**
```json
{
  "voice": {
    "provider": "playht",
    "voiceId": "jennifer"
  }
}
```

**After (Voice OS):**
```json
{
  "voice_id": "alloy",
  "voice_config": {
    "tts_provider": "openai",
    "stt_provider": "openai"
  }
}
```

### Voice Mapping Guide

Match your current voice personality:

| Vapi/PlayHT Voice | OpenAI Equivalent | Notes |
|-------------------|-------------------|-------|
| jennifer (female, professional) | alloy or echo | Neutral, professional |
| matthew (male, warm) | fable | Warm and engaging |
| adam (male, deep) | onyx | Authoritative, deep |
| sara (female, friendly) | nova | Energetic, friendly |
| emily (female, soft) | shimmer | Gentle, reassuring |

---

## Advanced Configuration

### Per-Call Voice Selection

```typescript
// In your CRM integration
const agent = await crmClient.getAgent(agentId);

// Override voice based on caller type
if (caller.type === 'VIP') {
  agent.voice_id = 'onyx'; // Authoritative
  agent.voice_config.tts_model = 'tts-1-hd'; // HD quality
} else if (caller.type === 'elderly') {
  agent.voice_id = 'shimmer'; // Gentle
  agent.voice_config.tts_speed = 0.9; // Slower
} else {
  agent.voice_id = 'alloy'; // Default
}
```

### Multi-Language Support

OpenAI Whisper supports 50+ languages automatically:

```bash
# Whisper auto-detects language
# No configuration needed!
```

Supported languages include:
- English, Spanish, French, German, Italian
- Portuguese, Polish, Dutch, Russian
- Japanese, Korean, Chinese
- And 40+ more

---

## Monitoring & Quality

### Track Voice Performance

```bash
# Check TTS metrics
curl http://localhost:8080/metrics | grep tts_latency
```

**Metrics to monitor:**
- `tts_latency_seconds` - How long TTS generation takes
- `tts_errors_total` - Failed TTS requests
- `tts_characters_total` - Character usage (for billing)

### Quality Checklist

- [ ] Voice sounds natural (not robotic)
- [ ] Speed is comfortable (0.9-1.1)
- [ ] Caller can understand clearly
- [ ] No audio clipping or distortion
- [ ] Latency under 500ms

### Common Issues

**Voice sounds choppy:**
- Check internet connection
- Verify server resources
- Consider upgrading to HD model

**Latency too high (>1 second):**
- Use standard model instead of HD
- Pre-generate common responses
- Check server location vs Twilio region

**Caller can't understand:**
- Slow down speed to 0.9
- Use simpler prompts
- Consider different voice

---

## Production Deployment

### Environment Variables

Full configuration for production:

```bash
# Voice Providers
STT_PROVIDER=openai
TTS_PROVIDER=openai

# Voice Settings
TTS_VOICE=alloy
OPENAI_TTS_MODEL=tts-1
OPENAI_TTS_SPEED=1.0

# OpenAI API
OPENAI_API_KEY=sk-...your-key-here...

# LLM Model
OPENAI_MODEL=gpt-4o
OPENAI_MAX_TOKENS=500
```

### Scaling Considerations

**100 hours/month:**
- Standard TTS: ~$81/month
- HD TTS: ~$162/month

**1,000 hours/month:**
- Standard TTS: ~$810/month
- HD TTS: ~$1,620/month

**10,000 hours/month:**
- Standard TTS: ~$8,100/month
- HD TTS: ~$16,200/month
- Consider negotiating enterprise pricing with OpenAI

---

## Migration from Vapi

### Step-by-Step Migration

1. **Keep Vapi Running** (no downtime)
2. **Set up Voice OS** with OpenAI
3. **Test on separate Twilio number**
4. **Compare quality and costs**
5. **Gradually migrate traffic**
6. **Cancel Vapi when confident**

### Side-by-Side Comparison

| Feature | Vapi | Voice OS (OpenAI) |
|---------|------|-------------------|
| Cost (1000hrs) | ~$10,000/month | ~$1,090/month |
| Voices | PlayHT (limited) | 6 OpenAI voices |
| STT | Deepgram | OpenAI Whisper |
| LLM | GPT-4o | GPT-4o (same) |
| Customization | Limited | Full control |
| API Keys | 1 (Vapi) | 2 (Twilio + OpenAI) |

**Savings: $8,910/month (89%)**

---

## Support & Resources

### OpenAI Documentation
- TTS API: https://platform.openai.com/docs/guides/text-to-speech
- Whisper API: https://platform.openai.com/docs/guides/speech-to-text
- Pricing: https://openai.com/pricing

### Voice Samples
Listen to voice samples: https://platform.openai.com/docs/guides/text-to-speech/voice-options

### Monitoring Costs
Track usage: https://platform.openai.com/usage

---

## Quick Reference

### Change Voice
```bash
# Edit .env
TTS_VOICE=fable

# Restart
npm run dev
```

### Enable HD Quality
```bash
# Edit .env
OPENAI_TTS_MODEL=tts-1-hd

# Restart
npm run dev
```

### Adjust Speed
```bash
# Edit .env
OPENAI_TTS_SPEED=0.9

# Restart
npm run dev
```

---

## Next Steps

1. ✅ **Test all 6 voices** - Find what fits your brand
2. ✅ **Set default in .env** - Configure your preferred voice
3. ✅ **Make test calls** - Verify quality
4. ✅ **Monitor costs** - Track OpenAI usage
5. ✅ **Get customer feedback** - Iterate based on responses

---

*Voice OS - Powered by OpenAI*
*Simple. Powerful. Cost-Effective.*
