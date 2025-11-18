from datetime import datetime

from nonebot import logger

from src.common.config import BotConfig

from .config import MailConfig, plugin_config
from .utils import send_mail

STATUS_COOLDOWN_KEY: str = "bot_status"


async def get_bot_admin_emails(bot_id: int) -> list[str]:
    """获取牛牛的admins邮箱列表"""
    emails: list[str] = []

    try:
        bot_config = BotConfig(bot_id=bot_id)
        admins = await bot_config._find("admins")

        # 为每个admin生成QQ邮箱
        if admins:
            emails.extend(f"{admin_id}@qq.com" for admin_id in admins)
    except Exception as e:
        logger.debug(f"Failed to get admins for bot {bot_id}: {e}")

    return emails


async def notify_bot_offline(bot_id: int, nickname: str, offline_reason: str = "") -> None:
    """通知牛牛离线"""

    # 获取admin邮箱列表
    admin_emails: list[str] = await get_bot_admin_emails(bot_id)

    # 构建邮件配置
    mail_config: MailConfig = MailConfig(
        user=plugin_config.bot_status_smtp_user,
        password=plugin_config.bot_status_smtp_password,
        server=plugin_config.bot_status_smtp_server,
        port=plugin_config.bot_status_smtp_port,
        notice_email=plugin_config.bot_status_notice_email,
    )

    # 发送邮件通知
    if mail_config.check_params():
        title: str = f"[牛牛不见啦] {nickname} 已离线 "

        reason_info = ""
        if offline_reason:
            reason_info = f"离线原因: {offline_reason}"

        content: str = f"""
{reason_info}

牛牛昵称：{nickname}
牛牛账号：{bot_id}
掉线时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


        """.strip()

        # 发送给配置的邮箱
        result: str | None = await send_mail(title, content, mail_config)
        if result:
            logger.error(f"Failed to send offline notification mail: {result}")
        else:
            logger.info(f"Offline notification mail sent for bot {bot_id}")

        # 发送给admin邮箱
        for email in admin_emails:
            try:
                admin_mail_config: MailConfig = MailConfig(
                    user=plugin_config.bot_status_smtp_user,
                    password=plugin_config.bot_status_smtp_password,
                    server=plugin_config.bot_status_smtp_server,
                    port=plugin_config.bot_status_smtp_port,
                    notice_email=email,
                )
                result = await send_mail(title, content, admin_mail_config)
                if result:
                    logger.error(f"Failed to send offline notification mail to admin {email}: {result}")
                else:
                    logger.info(f"Offline notification mail sent to admin {email} for bot {bot_id}")
            except Exception as e:
                logger.error(f"Exception occurred while sending mail to admin {email}: {e}")
    else:
        logger.warning("Mail configuration incomplete, cannot send offline notification")


async def handle_test_mail_command(bot, event) -> None:
    """处理测试邮件命令"""
    from nonebot.adapters.onebot.v11 import GroupMessageEvent
    from nonebot.matcher import Matcher

    if isinstance(event, GroupMessageEvent):
        from src.common.config import GroupConfig

        config = GroupConfig(group_id=event.group_id, cooldown=10)
        if not await config.is_cooldown(STATUS_COOLDOWN_KEY):
            return
        await config.refresh_cooldown(STATUS_COOLDOWN_KEY)

    mail_config: MailConfig = MailConfig(
        user=plugin_config.bot_status_smtp_user,
        password=plugin_config.bot_status_smtp_password,
        server=plugin_config.bot_status_smtp_server,
        port=plugin_config.bot_status_smtp_port,
        notice_email=plugin_config.bot_status_notice_email,
    )

    if not mail_config.check_params():
        missing_params: list[str] = []
        if not plugin_config.bot_status_smtp_user:
            missing_params.append("bot_status_smtp_user")
        if not plugin_config.bot_status_smtp_password:
            missing_params.append("bot_status_smtp_password")
        if not plugin_config.bot_status_smtp_server:
            missing_params.append("bot_status_smtp_server")
        if not plugin_config.bot_status_notice_email:
            missing_params.append("bot_status_notice_email")

        matcher = Matcher()
        await matcher.finish(f"邮箱配置缺少参数: {', '.join(missing_params)}")
        return

    title: str = "[Test]  这是一封测试邮件"
    content: str = f"""
牛牛在吗？

发送时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Bot ID: {bot.self_id}

如果你收到了这封邮件，证明邮箱配置正确。
    """.strip()

    result: str | None = await send_mail(title, content, mail_config)
    matcher = Matcher()
    if result:
        await matcher.finish(f"测试邮件发送失败: {result}")
    else:
        await matcher.finish("测试邮件发送成功！")
