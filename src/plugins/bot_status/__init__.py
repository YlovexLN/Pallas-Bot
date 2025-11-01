from datetime import datetime, timedelta

from nonebot import (
    get_bots,
    get_driver,
    logger,
    on_command,
    on_notice,
    require,
)
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent, NoticeEvent
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
offline_notice = on_notice(priority=5, block=False)
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


async def get_bot_nickname(bot_id: int, current_bots: dict = None) -> str:
    """获取牛牛昵称"""
    nickname: str = "Unknown Nickname"
    try:
        bots = current_bots if current_bots is not None else get_bots()
        if str(bot_id) in bots:
            try:
                info = await bots[str(bot_id)].call_api("get_stranger_info", user_id=bot_id)
                nickname = info.get("nickname", "Unknown Nickname")
                return nickname
            except Exception as e:
                logger.debug(f"Failed to get bot {bot_id} info using itself: {e}")

        for bot_instance in bots.values():
            if str(bot_id) != bot_instance.self_id:
                try:
                    info = await bot_instance.call_api("get_stranger_info", user_id=bot_id)
                    nickname = info.get("nickname", "Unknown Nickname")
                    break
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"Failed to get nickname for bot {bot_id}: {e}")

    return nickname


@driver.on_bot_disconnect
async def handle_bot_disconnect(bot: Bot) -> None:
    bot_id: int = int(bot.self_id)
    if bot_id in offline_bots and "source" in offline_bots[bot_id]:
        # 已经处理过了，直接返回
        return

    nickname: str = await get_bot_nickname(bot_id)

    offline_bots[bot_id] = {
        "nickname": nickname,
        "offline_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "disconnect_event",
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
        ],
        misfire_grace_time=60,
        coalesce=True,
        max_instances=1,
        trigger="date",
        run_date=run_time,
    )


@offline_notice.handle()
async def handle_bot_offline_events(event: NoticeEvent):
    """协议端离线事件"""
    bot_id = 0
    offline_message = ""
    source = ""

    if event.notice_type == "bot_offline":  # NapCat
        bot_id = event.user_id
        offline_message = getattr(event, "message", "")
        source = "napcat_event"
        logger.warning(f"NapCat Bot {bot_id} offline: {offline_message}")

    elif hasattr(event, "sub_type") and event.sub_type == "BotOfflineEvent":  # Lagrange
        bot_id = getattr(event, "self_id", getattr(event, "user_id", 0))
        offline_message = "Bot Offline"
        source = "lagrange_event"
        logger.warning(f"Lagrange Bot {bot_id} offline")

    if bot_id and source:
        # 先尝试获取昵称，如果获取不到再检查offline_bots
        try:
            nickname = await get_bot_nickname(bot_id)
        except Exception:
            # 如果无法获取昵称，检查offline_bots中是否已有信息
            if bot_id in offline_bots and "nickname" in offline_bots[bot_id]:
                nickname = offline_bots[bot_id]["nickname"]
            else:
                nickname = "Unknown Nickname"

        # 标记离线事件防止重复处理
        offline_bots[bot_id] = {
            "nickname": nickname,
            "offline_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
        }

        # 发送离线通知
        await notify_bot_offline(bot_id, nickname, offline_message)


async def check_bot_still_offline(bot_id: int, nickname: str) -> None:
    """检查牛牛是否真的离线"""
    bots = get_bots()
    if str(bot_id) not in bots:
        logger.warning(f"Bot {bot_id} offline, sending notification")
        # 更新离线时间
        if bot_id in offline_bots:
            offline_bots[bot_id]["offline_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            # 如果不在离线列表中，则添加进去
            offline_bots[bot_id] = {
                "nickname": nickname,
                "offline_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": "checked_offline",
            }
        await notify_bot_offline(bot_id, nickname)
    else:
        # 牛牛实际上在线，从离线列表中删除
        if (
            bot_id in offline_bots
            and "source" in offline_bots[bot_id]
            and offline_bots[bot_id]["source"] == "checked_offline"
        ):
            del offline_bots[bot_id]
        elif bot_id in offline_bots and "source" not in offline_bots[bot_id]:
            pass


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


async def notify_bot_offline(bot_id: int, nickname: str, offline_reason: str = "") -> None:
    """通知Bot离线"""

    # 获取admin邮箱列表
    admin_emails: list[str] = await get_bot_admin_emails(bot_id)

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


@bot_status_cmd.handle()
async def handle_bot_status(bot: Bot, event: MessageEvent) -> None:
    """处理状态查询命令"""
    if isinstance(event, GroupMessageEvent):
        config = GroupConfig(group_id=event.group_id, cooldown=10)
        if not await config.is_cooldown(STATUS_COOLDOWN_KEY):
            return
        await config.refresh_cooldown(STATUS_COOLDOWN_KEY)

    # 获取当前在线的牛牛
    current_bots = get_bots()

    all_bot_ids = set(block_config.bots) if block_config.bots else set()

    if not all_bot_ids:
        all_bot_ids.update(int(bot_id) for bot_id in current_bots.keys())

    all_bot_ids.update(offline_bots.keys())

    online_bots: dict[int, str] = {}
    offline_bots_filtered: dict[int, str] = {}

    for bot_id in all_bot_ids:
        if str(bot_id) in current_bots:
            nickname: str = await get_bot_nickname(bot_id, current_bots)
            online_bots[bot_id] = nickname
        else:
            # 从offline_bots中查找昵称信息
            if bot_id in offline_bots and "nickname" in offline_bots[bot_id]:
                nickname = offline_bots[bot_id]["nickname"]
            else:
                nickname = await get_bot_nickname(bot_id)
                # 更新offline_bots中的昵称信息
                if bot_id in offline_bots:
                    offline_bots[bot_id]["nickname"] = nickname
            offline_bots_filtered[bot_id] = nickname

    # 显示在线牛牛
    online_info: str = ""
    online_count: int = len(online_bots)
    if online_bots:
        bot_info_list: list[str] = [f"{nickname} ({bot_id})" for bot_id, nickname in online_bots.items()]
        online_info = f"在线的牛牛 (Total: {online_count}):\n" + "\n".join(bot_info_list)
    else:
        online_info = ""

    # 显示离线牛牛
    offline_info: str = ""
    offline_count: int = len(offline_bots_filtered)
    if offline_bots_filtered:
        offline_list: list[str] = [f"{nickname} ({bot_id})" for bot_id, nickname in offline_bots_filtered.items()]
        offline_info = f"\n\n离线的牛牛 (Total: {offline_count}):\n" + "\n".join(offline_list)

    if offline_info:
        message: str = online_info + offline_info
    else:
        message = online_info

    await bot_status_cmd.finish(message)
