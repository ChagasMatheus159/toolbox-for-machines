# Harness Prompt

Toolbox can generate a ready-to-use integration prompt for your AI agent or harness.

## Generate Your Prompt

```
GET /v1/harness-prompt
GET /v1/harness-prompt?toolbox_url=http://your-host:9600
```

This returns a complete markdown guide tailored to your deployment, including:

- Connection details
- All available tools with full schemas
- Integration patterns (Python examples)
- Constraints and best practices

Copy the returned prompt into your agent's system prompt or tool documentation.

## Manual Reference

If you prefer a static reference, see the [API documentation](docs/API.md) for endpoint details, or call `GET /v1/skills` for machine-readable tool definitions.
