# Built-in Signals

Adiuvare uses five built-in signal families by default. Once you know what each
one is for, score breakdowns stop feeling mysterious.

## Quick example

```text
score: 0.44
breakdown:
  payload: 0.32
  behavior: 0.07
  identity: 0.05
```

You can read that as: the content carried most of the risk, behavior added a
little pressure, and the identity already had some history.

## Payload

`payload` is the main content-focused signal family. It carries the most weight
for things like:

- SQL injection
- XSS
- path traversal
- encoded payload tricks that normalize into hostile input

Today it combines:

- libinjection SQLi checks
- libinjection XSS checks
- SQL pattern checks
- XSS pattern checks
- path traversal checks

### Payload coverage boundaries

Payload detection is intentionally focused on a narrow set of high-signal patterns.

#### Strong coverage

- SQL injection shapes such as `SELECT`, `UNION`, and simple tautologies
- XSS markers such as `<script>` and inline JavaScript patterns
- path traversal sequences like `../` and encoded variants

Detection is strongest when these appear directly or with light obfuscation.

#### Partial coverage

- less common injection techniques
- domain-specific payload formats
- heavily transformed or fragmented inputs

These may be detected inconsistently or assigned lower scores.

#### False positives

Literal use of risky strings can still contribute to payload scoring.

Common cases:

- documentation examples
- tutorials demonstrating SQL or HTML
- logs or debugging output containing payload-like text

Examples:

- "SELECT * FROM users"
- "<script>alert(1)</script>"

Payload signals contribute to the overall score. They are not a final decision on their own.

## Behavior

`behavior` is about request shape and request rate.

It looks at:

- how often the identity has shown up recently
- whether the user-agent looks obviously scripted
- missing or thin user-agent information

This is what helps when the payload is plain but the caller shape still looks
wrong.

## Identity

`identity` carries memory forward from earlier requests. It uses the identity
store and EWMA score so repeated noisy behavior can keep contributing risk even
when no single request looks dramatic on its own.

## Context

`context` is the small supporting signal based on where and how a request
lands.

Current checks include:

- critical route sensitivity
- unusual methods
- very large payloads
- hot route families such as `/admin` and `/auth`

It is intentionally smaller than `payload` or `identity`.

## ip_rep

`ip_rep` is a small IP reputation hint.

Right now it can react to:

- Tor exit hints from headers
- a short list of noisy network prefixes
- malformed IP parsing

Private and loopback addresses stay quiet here.

## Configurable weights

All five signal families are part of the scorer, but only three are
user-tunable in config:

- `payload`
- `behavior`
- `identity`

`context` and `ip_rep` still use fixed built-in weights.

## Reading another breakdown

```text
score: 0.21
breakdown:
  behavior: 0.11
  identity: 0.10
```

That usually means the request looked suspicious because of repetition or
caller shape, not because the payload itself looked explosive.

## Related

- [Configuration](configuration.md)
- [Custom signals](extending/custom-signals.md)
- [Signals API](api/signals.md)
