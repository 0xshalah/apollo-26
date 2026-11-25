# apollo26-flight-watch (Kiro Power)

Packages the Apollo-26 Flight Watch MCP server and the procedure an agent must follow into one installable Kiro Power, in the Agent Plugins format.

| File | Purpose |
| :-- | :-- |
| `plugin.json` | Manifest: name, version, keywords that activate the Power |
| `mcp.json` | Launches `scripts\mcp.cmd` from the Apollo-26 clone set in `APOLLO26_REPO` |
| `skills/flight-watch/SKILL.md` | The Flight Watch procedure and rules, loaded when a prompt mentions the keywords |

## Install
1. Clone the repository and finish the Python setup in the main README.
2. Set `APOLLO26_REPO` to the clone path, for example `setx APOLLO26_REPO C:\src\apollo-26`.
3. In Kiro IDE: Powers panel → **Add Custom Power** → **Import power from a folder** → choose `powers/apollo26-flight-watch`. Or import from the repository URL.
4. Kiro CLI: `kiro-cli powers install <path-to>/powers/apollo26-flight-watch`.

After install, Kiro prefixes the server name (for example `power-apollo26-flight-watch-apollo26`). The workspace custom agent `.kiro/agents/flight-director.json` uses the workspace MCP config instead, so both paths work independently.

The Power does not change the safety model: `execute_dsky_sequence` still goes through the MCP safety gate and the daemon guard, whichever client calls it.
