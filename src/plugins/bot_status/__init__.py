from datetime import datetime, timedelta

from nonebot import (
    get_bots,
    get_driver,
    logger,
    on_command,
    require,
)
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from src.common.config import BotConfig, GroupConfig
from src.plugins.block import plugin_config as block_config

from .config import MailConfig, plugin_config
from .utils import send_mail

__plugin_meta__ = PluginMetadata(
    name="牛牛状态查询",
    description="查询当前连接的Bot状态，检测Bot离线并发送通知",
    usage="""
牛牛在吗 - 查询当前连接的Bot列表
测试邮件 - 测试邮件发送功能
""",
    type="application",
    homepage="https://github.com/PallasBot",
    supported_adapters={"~onebot.v11"},
    extra={
        "version": "2.0.0",
        "menu_data": [
            {
                "func": "查看牛牛在线状况",
                "trigger_method": "on_message",
                "trigger_condition": "牛牛在吗",
                "brief_des": "总计牛牛在线情况",
                "detail_des": "当牛牛离线时发送离线通知邮件给号主与Superuser",
            },
            {
                "func": "发送测试邮件",
                "trigger_method": "on_message",
                "trigger_condition": "测试邮件",
                "brief_des": "发送测试邮件",
                "detail_des": "给配置中的邮箱发送测试邮件",
            },
        ],
        "menu_template": "default",
    },
)


STATUS_COOLDOWN_KEY: str = "bot_status"

bot_status_cmd = on_command("牛牛在吗", permission=SUPERUSER, priority=5, block=True)
test_mail_cmd = on_command("测试邮件", permission=SUPERUSER, priority=5, block=True)

scheduler = require("nonebot_plugin_apscheduler").scheduler

# 邮件配置
mail_config: MailConfig = MailConfig(
    user=plugin_config.bot_status_smtp_user,
    password=plugin_config.bot_status_smtp_password,
    server=plugin_config.bot_status_smtp_server,
    port=plugin_config.bot_status_smtp_port,
    notice_email=plugin_config.bot_status_notice_email,
)


offline_bots: dict[int, dict[str, str]] = {}

driver = get_driver()


@driver.on_startup
async def startup() -> None:
    logger.info("Bot_status is running")


@driver.on_bot_connect
async def handle_bot_connect(bot: Bot) -> None:
    bot_id: int = int(bot.self_id)
    if bot_id in offline_bots:
        del offline_bots[bot_id]


@driver.on_bot_disconnect
async def handle_bot_disconnect(bot: Bot) -> None:
    bot_id: int = int(bot.self_id)

    nickname: str = "Unknown"
    try:
        info = await bot.call_api("get_stranger_info", user_id=bot_id)
        nickname = info.get("nickname", "Unknown Nickname")
    except Exception as e:
        logger.debug(f"Failed to get bot {bot_id} info using itself: {e}")
        try:
            bots = get_bots()
            for bot_instance in bots.values():
                if str(bot_id) != bot_instance.self_id:
                    info = await bot_instance.call_api("get_stranger_info", user_id=bot_id)
                    nickname = info.get("nickname", "Unknown Nickname")
                    break
        except Exception as e:
            logger.debug(f"Failed to get bot {bot_id} info using other bots: {e}")

    offline_bots[bot_id] = {
        "nickname": nickname,
        "offline_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    job_id: str = f"bot_status_check_{bot_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    # 计算运行时间
    run_time: datetime = datetime.now() + timedelta(seconds=plugin_config.bot_status_offline_grace_time)

    scheduler.add_job(
        id=job_id,
        func=check_bot_still_offline,
        args=[
            bot_id,
            nickname,
            bot.adapter.get_name() if hasattr(bot.adapter, "get_name") else "Unknown Adapter",
        ],
        misfire_grace_time=60,
        coalesce=True,
        max_instances=1,
        trigger="date",
        run_date=run_time,
    )


async def check_bot_still_offline(bot_id: int, nickname: str, adapter_name: str) -> None:
    """检查Bot是否真的离线"""
    bots = get_bots()
    if str(bot_id) not in bots:
        logger.warning(f"Bot {bot_id} offline, sending notification")
        offline_bots[bot_id]["offline_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await notify_bot_offline(bot_id, nickname, adapter_name)
    else:
        if bot_id in offline_bots:
            del offline_bots[bot_id]


async def get_bot_admin_emails(bot_id: int) -> list[str]:
    """获取Bot的admins邮箱列表"""
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


@test_mail_cmd.handle()
async def handle_test_mail(bot: Bot, event: MessageEvent) -> None:
    """测试邮件"""
    if isinstance(event, GroupMessageEvent):
        config = GroupConfig(group_id=event.group_id, cooldown=10)
        if not await config.is_cooldown(STATUS_COOLDOWN_KEY):
            return
        await config.refresh_cooldown(STATUS_COOLDOWN_KEY)

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

        await test_mail_cmd.finish(f"邮箱配置缺少参数: {', '.join(missing_params)}")
        return

    title: str = "[Test]  这是一封测试邮件"
    content: str = f"""
牛牛在吗？

发送时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Bot ID: {bot.self_id}

如果你收到了这封邮件，证明邮箱配置正确。
    """.strip()

    result: str | None = await send_mail(title, content, mail_config)
    if result:
        await test_mail_cmd.finish(f"测试邮件发送失败: {result}")
    else:
        await test_mail_cmd.finish("测试邮件发送成功！")


async def notify_bot_offline(bot_id: int, nickname: str, adapter_name: str = "Unknown Adapter") -> None:
    """通知Bot离线"""
    # 获取admin邮箱列表
    admin_emails: list[str] = await get_bot_admin_emails(bot_id)

    # 发送邮件通知
    if mail_config.check_params():
        title: str = f"[牛牛不见啦] Bot {bot_id} is Offline"
        content: str = f"""
掉线通知
你的牛牛：{nickname}，账号：{bot_id}掉线啦，快去看看怎么回事吧
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


@bot_status_cmd.handle()
async def handle_bot_status(bot: Bot, event: MessageEvent) -> None:
    """处理Bot状态查询命令"""
    if isinstance(event, GroupMessageEvent):
        config = GroupConfig(group_id=event.group_id, cooldown=10)
        if not await config.is_cooldown(STATUS_COOLDOWN_KEY):
            return
        await config.refresh_cooldown(STATUS_COOLDOWN_KEY)

    current_bots = get_bots()

    # 显示在线Bot
    online_info: str = ""
    online_count: int = len(block_config.bots) if block_config.bots else 0
    if block_config.bots:
        bot_info_list: list[str] = []
        for bot_id in block_config.bots:
            if str(bot_id) in current_bots:
                nickname: str = "Unknown Nickname"
                try:
                    info = await bot.call_api("get_stranger_info", user_id=bot_id)
                    nickname = info.get("nickname", "Unknown Nickname")
                except Exception:
                    try:
                        for bot_instance in current_bots.values():
                            if str(bot_id) != bot_instance.self_id:
                                info = await bot_instance.call_api("get_stranger_info", user_id=bot_id)
                                nickname = info.get("nickname", "Unknown Nickname")
                                break
                    except Exception:
                        pass
                bot_info_list.append(f"{nickname} ({bot_id})")
            else:
                bot_info_list.append(f"Unknown Nickname ({bot_id})")

        online_info = f"当前在线的牛牛 (Total: {online_count}):\n" + "\n".join(bot_info_list)
    else:
        online_info = "No bots are currently online"

    offline_info: str = ""
    offline_count: int = len(offline_bots) if offline_bots else 0
    if offline_bots:
        offline_list: list[str] = []
        for bot_id, info in offline_bots.items():
            nickname = info["nickname"]
            if nickname == "Unknown" or nickname == "Unknown Nickname":
                # 如果之前是Unknown，尝试重新获取
                try:
                    for bot_instance in current_bots.values():
                        if str(bot_id) != bot_instance.self_id:
                            new_info = await bot_instance.call_api("get_stranger_info", user_id=bot_id)
                            nickname = new_info.get("nickname", "Unknown Nickname")
                            # 更新offline_bots中的昵称
                            offline_bots[bot_id]["nickname"] = nickname
                            break
                except Exception:
                    pass

            offline_list.append(f"{nickname} ({bot_id})")
        offline_info = f"\n\n离线的牛牛 (Total: {offline_count}):\n" + "\n".join(offline_list)

    if offline_info:
        message: str = online_info + offline_info
    elif online_info:
        message = online_info
    else:
        message = "No bots are currently online or offline"

    await bot_status_cmd.finish(message)
