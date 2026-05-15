# kira-ai-plugin-email

Email plugin for KiraAI — empower your digital life with email capabilities.

## Features

- **Send Emails** — Compose and send emails via SMTP with a simple tool call
- **Check Inbox** — Fetch recent emails from your inbox via IMAP
- **Configurable** — Full WebUI configuration support (SMTP, IMAP, signature, recipient whitelist)
- **Secure** — SSL/TLS support, authorization code authentication, optional recipient whitelist

## Installation

1. Copy this entire folder into your KiraAI `data/plugins/` directory.
2. Restart KiraAI or reload plugins from the WebUI.
3. Configure your email settings in the WebUI plugin settings panel.

## Configuration

| Field | Type | Description |
|-------|------|-------------|
| `smtp_host` | string | SMTP server address (default: `smtp.qq.com`) |
| `smtp_port` | integer | SMTP port (default: `465` for SSL) |
| `smtp_use_ssl` | switch | Use SSL for SMTP connection |
| `imap_host` | string | IMAP server address (default: `imap.qq.com`) |
| `imap_port` | integer | IMAP port (default: `993`) |
| `email_address` | string | Your email address |
| `email_password` | sensitive | SMTP/IMAP authorization code (not login password) |
| `default_signature` | textarea | Signature appended to every outgoing email |
| `max_inbox_count` | integer | Maximum emails to fetch when checking inbox (1-50) |
| `allowed_recipients` | list | Whitelist of allowed recipient addresses (empty = no restriction) |

## Tools

### `send_email`

Send an email to one or more recipients.

**Parameters:**
- `to` (required) — Recipient email address(es), comma-separated
- `subject` (required) — Email subject
- `body` (required) — Plain text email body
- `cc` (optional) — CC recipients, comma-separated

### `check_inbox`

Fetch recent emails from the inbox.

**Parameters:**
- `count` (optional) — Number of emails to fetch; defaults to `max_inbox_count`

## License

AGPL 3.0 — same as KiraAI.
