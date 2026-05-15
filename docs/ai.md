# AI Integration

Adiuvare can ask an external Ollama-compatible model for a second opinion
during `trackB`. It is there to supplement the normal scoring path, not replace
it.

## Quick example

```yaml
ai:
  enabled: true
  mode: assist
  model: llama3
  base_url: http://127.0.0.1:11434
  timeout_secs: 5.0
```

```python
@app.post("/review")
@guard.protect(ai_mode="critical", sensitivity="critical")
async def review():
    return {"ok": True}
```

That gives one route a stronger AI-backed review path without turning AI on
everywhere at once.

## Where AI fits

The request-time AI path is part of the soft pipeline. It adds a bounded hint
on top of payload, behavior, identity, context, and IP hints.

The TUI has a separate operator-side AI surface:

- `Analyze` for compact report-style summaries
- `Ask` for bounded operator questions

Those are related to the runtime AI path, but they are not the same feature.

## Config

```yaml
ai:
  enabled: false
  mode: off
  model: llama3
  base_url: http://127.0.0.1:11434
  api_key:
  timeout_secs: 5.0
```

The important fields are:

| field | meaning |
| --- | --- |
| `enabled` | convenience flag for whether AI is effectively on |
| `mode` | `off`, `assist`, `critical`, or `async` |
| `model` | model name sent to the endpoint |
| `base_url` | Ollama-compatible base URL |
| `api_key` | optional auth value if your endpoint needs one |
| `timeout_secs` | how long to wait before degrading cleanly |

Environment overrides:

```bash
export ADIUVARE_AI_MODE=assist
export ADIUVARE_AI_BASE_URL=http://127.0.0.1:11434
export ADIUVARE_AI_MODEL=llama3
```

## Normal setup flow

For a local Ollama-style setup:

1. start the endpoint
2. make sure the model you want is available
3. set `model`, `base_url`, and `timeout_secs`
4. enable AI on selected routes first

Example:

```bash
ollama pull llama3
```

```yaml
ai:
  enabled: true
  mode: assist
  model: llama3
  base_url: http://127.0.0.1:11434
  timeout_secs: 5.0
```

You are not locked to `llama3`. Any Ollama-compatible model exposed by your
endpoint can work here.

## What gets sent

The runtime prompt uses a compact summary of the request, including things like:

- endpoint
- prior score
- a clipped payload sample

The AI path asks for structured output with:

- `verdict`
- `confidence`
- `reason`

The current verdict labels are:

- `clean`
- `suspicious`
- `malicious`

Those get translated into a bounded score hint. AI does not take over the whole
decision engine by itself.

## Example result shape

```text
reason: ai_suspicious
score: 0.12
detail.verdict: suspicious
detail.confidence: 0.68
```

That is the point of the feature: one more opinion, not a separate verdict
system trying to override everything else.

## Failure behavior

If the AI request fails:

- timeout -> `ai_timeout`
- other exception -> `ai_error`
- mode off -> `ai_off`

The request path degrades cleanly instead of exploding.

## TUI AI screens

### Analyze

Analyze builds a compact recent-window report from audit rows. The result can
come from runtime AI or local analysis fallback, and the screen shows that
source clearly.

### Ask

Ask is the bounded operator assistant. It is meant for questions like:

- what are the top threats?
- who is most active?
- should I change thresholds?
- explain payload signals

The Ask header shows:

- whether the TUI is connected to the runtime
- which model is configured
- that model reachability is not checked by this header
- whether local fallback is available

Runtime connection means the operator console can reach the Adiuvare runtime
snapshot/command surface. It should not be read as proof that the configured
model endpoint is reachable.

## Good rollout shape

The safest rollout is still:

1. leave global AI mode off
2. enable AI on one or two higher-risk routes
3. watch event detail and the TUI AI screens
4. decide whether `assist` is enough or whether a stricter route-level mode helps

That keeps the AI path useful without making it feel magical.

## Limits

- Adiuvare depends on an external model endpoint
- report and ask flows may fall back to local analysis
- AI is a supplement to the score, not a replacement for hard request controls

## Related

- [Configuration](configuration.md)
- [TUI](operator/tui.md)
- [Route policies](extending/route-policies.md)
- [Limitations](limitations.md)
