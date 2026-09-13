# Privacy

Stitch Design for Codex does not collect, store, sell, or independently transmit user data. It packages local Agent Skills and configures a connection from the user's Codex client to Google Stitch.

When a user invokes Stitch MCP tools, prompts, project identifiers, uploaded assets, and generated design data may be sent directly to Google Stitch under the user's account and Google's applicable terms and privacy policy. The plugin authors do not receive that traffic.

Users provide their own `STITCH_API_KEY`. The plugin does not contain or intentionally print a key. The cross-platform `scripts/stitch_setup.py setup` flow stores it in a restricted current-user configuration file: Unix uses `$XDG_CONFIG_HOME/stitch-design/credentials.json` or `~/.config/stitch-design/credentials.json`, and Windows uses `%APPDATA%\stitch-design\credentials.json`. This file is permission-restricted but is not an encrypted vault.

The local stdio proxy reads the key once per process, excludes it from debug representations, and sends it only to the exact Google Stitch HTTPS origin. Only HTTP 401 refreshes the cached value and retries once. HTTP 403 is permission denied and is not refreshed or replayed. Users remain responsible for securing, rotating, and revoking credentials.

Harness receipts contain provider/tool identifiers, local artifact paths, hashes, dimensions, gate results, and user approval evidence. They exclude API keys, cookies, authorization headers, base64 bodies, and signed download URLs. These receipts remain in the user's business project unless the user moves or deletes them.

Local scripts process only files and locations authorized by the user. Static HTML extraction includes private-network request controls, URL redaction, and output escaping, but users should still inspect generated artifacts before sharing them.

Security or privacy concerns may be reported through the repository's GitHub Issues page without including credentials, private project data, or signed URLs.
