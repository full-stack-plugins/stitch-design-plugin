# Privacy

Stitch Design for Codex does not collect, store, sell, or independently transmit user data. It packages local Agent Skills and configures a connection from the user's Codex client to Google Stitch.

When a user invokes Stitch MCP tools, prompts, project identifiers, uploaded assets, and generated design data may be sent directly to Google Stitch under the user's account and Google's applicable terms and privacy policy. The plugin authors do not receive that traffic.

Users provide their own `STITCH_API_KEY`. The plugin does not contain or intentionally print a key. The optional cross-platform `scripts/stitch_setup.py setup` flow stores it in a dedicated file under the current user's configuration directory; Unix directories use mode `0700` and files use `0600`, while Windows uses the current user's `APPDATA` directory and inherited ACLs. This is a permission-restricted file, not an encrypted system credential vault. Launch commands read it only to inject `STITCH_API_KEY` into the target child process. Users remain responsible for securing, rotating, and revoking credentials.

Local scripts process only files and locations authorized by the user. Static HTML extraction includes private-network request controls, URL redaction, and output escaping, but users should still inspect generated artifacts before sharing them.

Security or privacy concerns may be reported through the repository's GitHub Issues page without including credentials, private project data, or signed URLs.
