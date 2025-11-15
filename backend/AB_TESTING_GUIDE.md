# A/B Testing Framework - Complete Guide

## Overview

The A/B Testing Framework enables you to scientifically test and optimize AI performance by running controlled experiments on:
- **AI Prompts** - Test different system prompts, few-shot examples, instructions
- **LLM Models** - Compare Claude vs GPT-4, different model versions
- **Agent Configurations** - Test confidence thresholds, parameters, tool selections
- **Features** - Test new features vs existing workflows
- **UI/UX** - Test interface changes

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User/Session Request                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│            ExperimentService.get_variant_for_user()          │
│  - Checks if user in experiment                              │
│  - Returns assigned variant (or assigns new one)             │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│         Use Variant Configuration (e.g., prompt)             │
│  - Apply experimental settings                               │
│  - Generate AI response                                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│         ExperimentService.record_result()                    │
│  - Record metrics (resolution_rate, satisfaction, etc.)      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│      StatisticalAnalyzer.analyze_experiment()                │
│  - Calculate p-value, significance                           │
│  - Recommend winner                                          │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Create an Experiment

```bash
curl -X POST http://localhost:8000/api/v1/experiments/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Lead Qualification Prompt Test",
    "description": "Testing new prompt with few-shot examples vs current prompt",
    "experiment_type": "prompt",
    "primary_metric": "resolution_rate",
    "secondary_metrics": ["satisfaction_score", "response_time"],
    "variants": [
      {
        "name": "Control",
        "is_control": true,
        "traffic_allocation": 50.0,
        "config": {
          "system_prompt": "You are an AI assistant for mortgage CRM...",
          "include_examples": false
        }
      },
      {
        "name": "Treatment - Few Shot Examples",
        "is_control": false,
        "traffic_allocation": 50.0,
        "config": {
          "system_prompt": "You are an AI assistant for mortgage CRM...",
          "include_examples": true,
          "examples": [
            "User: What documents do I need? Assistant: For a purchase loan, you'll need...",
            "User: How long does approval take? Assistant: Typically 3-5 business days..."
          ]
        }
      }
    ],
    "target_percentage": 100.0,
    "min_sample_size": 100,
    "confidence_level": 0.95
  }'
```

Response:
```json
{
  "id": 1,
  "name": "Lead Qualification Prompt Test",
  "status": "draft",
  "message": "Experiment created successfully. Use /start endpoint to begin."
}
```

### 2. Start the Experiment

```bash
curl -X POST http://localhost:8000/api/v1/experiments/1/start
```

Response:
```json
{
  "message": "Experiment 1 started successfully"
}
```

### 3. Get Variant Assignment

In your AI service code:

```python
from ab_testing.experiment_service import ExperimentService

service = ExperimentService(db)

# Get variant for this user
variant = service.get_variant_for_user(
    experiment_name="Lead Qualification Prompt Test",
    user_id=123,
    session_id=None  # Or provide session_id for anonymous users
)

if variant:
    # Use experimental configuration
    system_prompt = variant['config']['system_prompt']
    include_examples = variant['config'].get('include_examples', False)

    # Generate AI response using variant config
    # ...
else:
    # Use default configuration
    # ...
```

### 4. Record Results

After generating AI response and measuring metrics:

```python
# Record resolution rate
service.record_result(
    experiment_name="Lead Qualification Prompt Test",
    metric_name="resolution_rate",
    metric_value=1.0,  # 1.0 = resolved, 0.0 = not resolved
    user_id=123,
    session_id=None
)

# Record satisfaction score
service.record_result(
    experiment_name="Lead Qualification Prompt Test",
    metric_name="satisfaction_score",
    metric_value=4.5,  # 0-5 scale
    user_id=123,
    session_id=None
)
```

### 5. Analyze Results

```bash
curl http://localhost:8000/api/v1/experiments/1/analyze
```

Response:
```json
{
  "experiment_id": 1,
  "analysis_date": "2025-01-15T10:30:00Z",
  "variant_stats": {
    "1": {
      "mean": 0.72,
      "std": 0.15,
      "count": 150,
      "min": 0.4,
      "max": 1.0
    },
    "2": {
      "mean": 0.85,
      "std": 0.12,
      "count": 148,
      "min": 0.5,
      "max": 1.0
    }
  },
  "p_value": 0.01,
  "is_significant": true,
  "recommended_winner_id": 2,
  "recommendation_confidence": 0.95,
  "recommendation_reason": "Variant 2 shows 18.1% improvement with 148 samples. Mean: 0.850 (vs control: 0.720)",
  "sufficient_sample_size": true,
  "current_sample_size": 298,
  "required_sample_size": 100
}
```

### 6. Stop Experiment and Declare Winner

```bash
curl -X POST "http://localhost:8000/api/v1/experiments/1/stop?declare_winner=true"
```

## Experiment Types

### 1. Prompt Experiments

Test different AI prompts:

```python
{
  "experiment_type": "prompt",
  "variants": [
    {
      "name": "Control",
      "config": {
        "system_prompt": "Current prompt...",
        "temperature": 0.7
      }
    },
    {
      "name": "Treatment",
      "config": {
        "system_prompt": "New prompt with structured format...",
        "temperature": 0.7,
        "include_examples": true,
        "examples": ["Example 1", "Example 2"]
      }
    }
  ]
}
```

### 2. Model Experiments

Compare different LLM models:

```python
{
  "experiment_type": "model",
  "variants": [
    {
      "name": "Claude 3.5 Sonnet",
      "config": {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 2000
      }
    },
    {
      "name": "GPT-4",
      "config": {
        "provider": "openai",
        "model": "gpt-4-turbo-preview",
        "max_tokens": 2000
      }
    }
  ]
}
```

### 3. Agent Configuration Experiments

Test different agent parameters:

```python
{
  "experiment_type": "agent_config",
  "variants": [
    {
      "name": "Conservative",
      "config": {
        "confidence_threshold": 0.95,
        "auto_approve": false,
        "max_retries": 2
      }
    },
    {
      "name": "Aggressive",
      "config": {
        "confidence_threshold": 0.85,
        "auto_approve": true,
        "max_retries": 3
      }
    }
  ]
}
```

### 4. Feature Experiments

Test new features vs existing:

```python
{
  "experiment_type": "feature",
  "variants": [
    {
      "name": "Existing Workflow",
      "config": {
        "enable_smart_routing": false,
        "use_ai_suggestions": false
      }
    },
    {
      "name": "New AI-Powered Workflow",
      "config": {
        "enable_smart_routing": true,
        "use_ai_suggestions": true,
        "suggestion_threshold": 0.8
      }
    }
  ]
}
```

## Metrics to Track

### Primary Metrics

Choose ONE primary metric to optimize:

- **resolution_rate** - % of inquiries successfully resolved by AI
- **satisfaction_score** - User satisfaction rating (0-5 scale)
- **conversion_rate** - % of leads that convert
- **response_accuracy** - Accuracy of AI responses (0-1)
- **escalation_rate** - % of interactions escalated to humans (lower is better)

### Secondary Metrics

Track additional metrics for context:

- **response_time** - Time to generate response (seconds)
- **token_usage** - LLM tokens used (cost metric)
- **first_contact_resolution** - Resolved on first interaction
- **context_relevance** - How well AI used past context (0-1)

## Best Practices

### 1. Experiment Design

✅ **DO:**
- Start with 50/50 traffic split for 2 variants
- Set realistic sample size (100-1000+ depending on traffic)
- Run experiments for at least 1 week to capture daily patterns
- Test one change at a time (isolated variables)
- Define success metrics BEFORE starting

❌ **DON'T:**
- Don't run too many experiments simultaneously (max 2-3)
- Don't stop experiments too early (wait for significance)
- Don't test multiple changes in one experiment
- Don't ignore seasonality/day-of-week effects

### 2. Statistical Significance

- **p-value < 0.05** = Statistically significant (95% confidence)
- **p-value < 0.01** = Highly significant (99% confidence)
- **p-value ≥ 0.05** = Not significant, need more data

**Sample Size Guidelines:**
- Small effect (2-5% improvement): Need 1000+ samples
- Medium effect (5-10% improvement): Need 500+ samples
- Large effect (10%+ improvement): Need 100+ samples

### 3. Interpreting Results

```
Example Results:
- Control: resolution_rate = 0.72 (150 samples)
- Treatment: resolution_rate = 0.85 (148 samples)
- Improvement: 18.1%
- p-value: 0.01 ✅ (significant)

ACTION: Promote Treatment variant to all users
```

```
Example Results:
- Control: resolution_rate = 0.72 (50 samples)
- Treatment: resolution_rate = 0.75 (52 samples)
- Improvement: 4.2%
- p-value: 0.20 ❌ (not significant)

ACTION: Continue collecting data or declare no winner
```

## Integration Examples

### Example 1: Prompt Testing in AI Memory Service

See `ai_memory_service_with_ab_testing.py` for full implementation.

```python
# In your AI service
variant = experiment_service.get_variant_for_user(
    experiment_name="lead_qualification_prompt",
    user_id=user_id
)

if variant:
    # Use experimental prompt
    system_prompt = variant['config']['system_prompt']
else:
    # Use default prompt
    system_prompt = get_default_prompt()

# Generate response
response = claude_client.messages.create(
    model="claude-3-5-sonnet-20241022",
    system=system_prompt,
    messages=[{"role": "user", "content": message}]
)

# Record results
experiment_service.record_result(
    experiment_name="lead_qualification_prompt",
    metric_name="resolution_rate",
    metric_value=1.0 if successful else 0.0,
    user_id=user_id
)
```

### Example 2: Model Comparison

```python
variant = experiment_service.get_variant_for_user(
    experiment_name="claude_vs_gpt4",
    user_id=user_id
)

if variant['config']['provider'] == 'anthropic':
    response = anthropic_client.messages.create(...)
elif variant['config']['provider'] == 'openai':
    response = openai_client.chat.completions.create(...)

# Record metrics
experiment_service.record_result(
    experiment_name="claude_vs_gpt4",
    metric_name="response_quality",
    metric_value=quality_score,
    user_id=user_id
)
```

## API Reference

### Create Experiment
`POST /api/v1/experiments/`

### Start Experiment
`POST /api/v1/experiments/{id}/start`

### Stop Experiment
`POST /api/v1/experiments/{id}/stop?declare_winner=true`

### Get Variant
`POST /api/v1/experiments/get-variant`

### Record Result
`POST /api/v1/experiments/record-result`

### Analyze Experiment
`GET /api/v1/experiments/{id}/analyze`

### Get Summary
`GET /api/v1/experiments/{id}/summary`

### List Experiments
`GET /api/v1/experiments/?status=running&experiment_type=prompt`

## Database Schema

### Tables Created

1. **ab_experiments** - Experiment definitions
2. **ab_variants** - Variant configurations
3. **ab_assignments** - User/session assignments
4. **ab_results** - Individual metric measurements
5. **ab_insights** - Statistical analysis results

## Monitoring

### Key Metrics to Monitor

```sql
-- Check experiment progress
SELECT
  e.name,
  e.status,
  COUNT(DISTINCT a.user_id) as users_assigned,
  COUNT(r.id) as results_collected
FROM ab_experiments e
LEFT JOIN ab_assignments a ON e.id = a.experiment_id
LEFT JOIN ab_results r ON e.id = r.experiment_id
WHERE e.status = 'running'
GROUP BY e.id, e.name, e.status;
```

```sql
-- View variant performance
SELECT
  v.name as variant_name,
  AVG(r.metric_value) as avg_metric,
  COUNT(*) as sample_size
FROM ab_variants v
JOIN ab_results r ON v.id = r.variant_id
WHERE r.experiment_id = 1 AND r.metric_name = 'resolution_rate'
GROUP BY v.id, v.name;
```

## Troubleshooting

### Issue: Not enough samples

**Solution:** Lower `min_sample_size` or run experiment longer

### Issue: No variant assignment

**Solution:** Check experiment status is "running", verify user_id/session_id

### Issue: p-value always high (not significant)

**Solution:** Effect size too small, need more samples, or variants perform similarly

### Issue: Inconsistent results

**Solution:** Check for external factors (time of day, day of week), ensure deterministic assignment

## Next Steps

1. **Create your first experiment** - Start with a simple prompt test
2. **Monitor daily** - Check experiment progress and sample collection
3. **Analyze weekly** - Run statistical analysis once sufficient data
4. **Promote winners** - Deploy successful variants to all users
5. **Iterate** - Start new experiments to continually improve

## Support

For questions or issues:
- Check this guide
- Review example code in `ai_memory_service_with_ab_testing.py`
- Check experiment logs: `grep "experiment" backend/logs/`
