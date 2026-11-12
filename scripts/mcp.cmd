@echo off
rem Launches the Apollo-26 MCP stdio server from the repository root (used by .kiro/settings/mcp.json).
rem stdout is reserved for MCP JSON-RPC; never echo anything here.
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m mcp_server.server --rpc-port 8027 %*
