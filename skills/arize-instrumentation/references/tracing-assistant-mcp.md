# Tracing Assistant MCP

Consult this when the user asks about IDE-based instrumentation guidance or wants to set up MCP integrations for Arize.

For deeper instrumentation guidance inside the IDE, the user can enable:

- **Arize AX Tracing Assistant MCP** — instrumentation guides, framework examples, and support. In Cursor: **Settings → MCP → Add** and use:
  ```json
  "arize-tracing-assistant": {
    "command": "uvx",
    "args": ["arize-tracing-assistant@latest"]
  }
  ```
- **Arize AX Docs MCP** — searchable docs. In Cursor:
  ```json
  "arize-ax-docs": {
    "url": "https://arize.com/docs/mcp"
  }
  ```

Then the user can ask things like: *"Instrument this app using Arize AX"*, *"Can you use manual instrumentation so I have more control over my traces?"*, *"How can I redact sensitive information from my spans?"*

See the full setup at [Agent-Assisted Tracing Setup](https://arize.com/docs/ax/alyx/tracing-assistant).
