"""
KiraAI 邮件插件 (kira-ai-plugin-email)
为数字生命提供邮件收发能力
"""
import asyncio
import email
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

from core.plugin import BasePlugin, PluginContext, on, Priority, register
from core.chat import KiraMessageEvent, KiraMessageBatchEvent
from core.provider import ToolResult
from core.chat.message_elements import Text

logger = logging.getLogger(__name__)


class EmailPlugin(BasePlugin):
    """接入邮件系统的 KiraAI 插件"""

    def __init__(self, ctx: PluginContext, cfg: dict):
        super().__init__(ctx, cfg)
        self._check_task: asyncio.Task | None = None
        self._last_uid: int = 0
        self._data_dir: Path | None = None

    # ── 生命周期 ──────────────────────────────────────────

    async def initialize(self):
        """插件加载时初始化"""
        self._data_dir = self.ctx.get_plugin_data_dir()

        # 检查必要配置
        addr = self.plugin_cfg.get("email_address", "")
        pwd = self.plugin_cfg.get("email_password", "")
        if not addr or not pwd:
            logger.warning("邮件插件：邮箱地址或授权码未配置，插件已加载但邮件功能不可用")
        else:
            logger.info(f"邮件插件已初始化，邮箱: {addr}")

    async def terminate(self):
        """插件卸载时释放资源"""
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            self._check_task = None
        logger.info("邮件插件已卸载")

    # ── 辅助方法 ──────────────────────────────────────────

    def _get_config(self):
        """获取邮件配置"""
        return {
            "smtp_host": self.plugin_cfg.get("smtp_host", "smtp.qq.com"),
            "smtp_port": self.plugin_cfg.get("smtp_port", 465),
            "smtp_use_ssl": self.plugin_cfg.get("smtp_use_ssl", True),
            "imap_host": self.plugin_cfg.get("imap_host", "imap.qq.com"),
            "imap_port": self.plugin_cfg.get("imap_port", 993),
            "address": self.plugin_cfg.get("email_address", ""),
            "password": self.plugin_cfg.get("email_password", ""),
            "signature": self.plugin_cfg.get("default_signature", ""),
            "max_count": self.plugin_cfg.get("max_inbox_count", 10),
            "allowed": self.plugin_cfg.get("allowed_recipients", []),
        }

    # ── 工具：发送邮件 ────────────────────────────────────

    @register.tool(
        name="send_email",
        description="发送电子邮件。需要提供收件人地址、邮件主题和正文内容。",
        params={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "收件人邮箱地址，多个地址用英文逗号分隔",
                },
                "subject": {
                    "type": "string",
                    "description": "邮件主题",
                },
                "body": {
                    "type": "string",
                    "description": "邮件正文（纯文本）",
                },
                "cc": {
                    "type": "string",
                    "description": "抄送地址，可选，多个用逗号分隔",
                },
            },
            "required": ["to", "subject", "body"],
        },
    )
    async def send_email(
        self,
        event: KiraMessageBatchEvent,
        *_,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
    ) -> str:
        """发送邮件"""
        cfg = self._get_config()

        if not cfg["address"] or not cfg["password"]:
            return "❌ 邮件发送失败：邮箱未配置，请在 WebUI 中设置邮箱地址和授权码。"

        # 收件人白名单检查
        allowed = cfg["allowed"]
        if allowed:
            recipients = [r.strip() for r in to.split(",")]
            for r in recipients:
                if r not in allowed:
                    return f"❌ 邮件发送失败：收件人 {r} 不在允许列表中。"

        try:
            # 构建邮件
            msg = MIMEMultipart()
            msg["From"] = cfg["address"]
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc

            # 正文 + 签名
            full_body = body + cfg["signature"]
            msg.attach(MIMEText(full_body, "plain", "utf-8"))

            # 发送
            await asyncio.to_thread(self._send_via_smtp, cfg, msg, to, cc)

            cc_info = f"，抄送: {cc}" if cc else ""
            return f"✅ 邮件已发送！\n收件人: {to}{cc_info}\n主题: {subject}"

        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return f"❌ 邮件发送失败: {e}"

    def _send_via_smtp(self, cfg: dict, msg: MIMEMultipart, to: str, cc: str):
        """通过 SMTP 发送邮件（同步操作，在 executor 中运行）"""
        import smtplib

        if cfg["smtp_use_ssl"]:
            server = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"])
        else:
            server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"])
            server.starttls()

        server.login(cfg["address"], cfg["password"])
        all_recipients = [r.strip() for r in to.split(",")]
        if cc:
            all_recipients += [r.strip() for r in cc.split(",")]
        server.sendmail(cfg["address"], all_recipients, msg.as_string())
        server.quit()

    # ── 工具：查看收件箱 ──────────────────────────────────

    @register.tool(
        name="check_inbox",
        description="查看收件箱中的最近邮件。返回发件人、主题和日期信息。",
        params={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "查看的邮件数量，默认使用配置中的 max_inbox_count",
                }
            },
            "required": [],
        },
    )
    async def check_inbox(
        self,
        event: KiraMessageBatchEvent,
        *_,
        count: int | None = None,
    ) -> str:
        """查看收件箱"""
        cfg = self._get_config()

        if not cfg["address"] or not cfg["password"]:
            return "❌ 无法查看收件箱：邮箱未配置。"

        if count is None:
            count = cfg["max_count"]
        count = min(count, 50)  # 最多 50 封

        try:
            emails = await asyncio.to_thread(self._fetch_inbox, cfg, count)
        except Exception as e:
            logger.error(f"获取收件箱失败: {e}")
            return f"❌ 获取收件箱失败: {e}"

        if not emails:
            return "📭 收件箱为空~"

        result_lines = [f"📬 收件箱（最近 {len(emails)} 封）:"]
        for i, (sender, subject, date_str) in enumerate(emails, 1):
            # 解码主题
            try:
                decoded_parts = email.header.decode_header(subject)
                subject_str = ""
                for part, charset in decoded_parts:
                    if isinstance(part, bytes):
                        subject_str += part.decode(charset or "utf-8", errors="replace")
                    else:
                        subject_str += part
            except Exception:
                subject_str = subject or "(无主题)"

            result_lines.append(f"\n{i}. 📧 {sender}")
            result_lines.append(f"   主题: {subject_str}")
            result_lines.append(f"   时间: {date_str}")

        return "\n".join(result_lines)

    def _fetch_inbox(self, cfg: dict, count: int) -> list[tuple[str, str, str]]:
        """通过 IMAP 获取收件箱（同步操作）"""
        import imaplib

        server = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
        server.login(cfg["address"], cfg["password"])
        server.select("INBOX")

        # 搜索所有邮件
        status, messages = server.search(None, "ALL")
        if status != "OK":
            server.logout()
            return []

        msg_ids = messages[0].split()
        # 取最近 count 封
        recent_ids = msg_ids[-count:] if len(msg_ids) > count else msg_ids
        recent_ids.reverse()  # 最新在前面

        results = []
        for mid in recent_ids:
            status, msg_data = server.fetch(mid, "(RFC822.HEADER)")
            if status != "OK":
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender = msg.get("From", "未知")
            subject = msg.get("Subject", "(无主题)")
            date_str = msg.get("Date", "未知")

            results.append((sender, subject, date_str))

        server.logout()
        return results


# ── 插件入口 ──────────────────────────────────────────────
plugin_class = EmailPlugin
