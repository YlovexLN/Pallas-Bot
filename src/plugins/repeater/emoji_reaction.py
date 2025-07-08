import random

from nonebot import get_plugin_config, logger, on_message
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.exception import ActionFailed
from nonebot.rule import Rule
from nonebot.typing import T_State

from .config import Config

EMOJI_IDS = (
    4,
    5,
    8,
    9,
    10,
    12,
    14,
    16,
    21,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    32,
    33,
    34,
    38,
    39,
    41,
    42,
    43,
    49,
    53,
    60,
    63,
    66,
    74,
    75,
    76,
    78,
    79,
    85,
    89,
    96,
    97,
    98,
    99,
    100,
    101,
    102,
    103,
    104,
    106,
    109,
    111,
    116,
    118,
    120,
    122,
    123,
    124,
    125,
    129,
    144,
    147,
    171,
    173,
    174,
    175,
    176,
    179,
    180,
    181,
    182,
    183,
    201,
    203,
    212,
    214,
    219,
    222,
    227,
    232,
    240,
    243,
    246,
    262,
    264,
    265,
    266,
    267,
    268,
    269,
    270,
    271,
    272,
    273,
    278,
    281,
    282,
    284,
    285,
    287,
    289,
    290,
    293,
    294,
    297,
    298,
    299,
    305,
    306,
    307,
    314,
    315,
    318,
    319,
    320,
    322,
    324,
    326,
    9728,
    9749,
    9786,
    10024,
    10060,
    10068,
    127801,
    127817,
    127822,
    127827,
    127836,
    127838,
    127847,
    127866,
    127867,
    127881,
    128027,
    128046,
    128051,
    128053,
    128074,
    128076,
    128077,
    128079,
    128089,
    128102,
    128104,
    128147,
    128157,
    128164,
    128166,
    128168,
    128170,
    128235,
    128293,
    128513,
    128514,
    128516,
    128522,
    128524,
    128527,
    128530,
    128531,
    128532,
    128536,
    128538,
    128540,
    128541,
    128557,
    128560,
    128563,
)  # 官方文档就这么多


SUPPORTED_PROTOCOLS = ("Lagrange", "NapCat")  # 一统天下的日子还没来吗
last_successful_protocol: dict[str, str] = {}
plugin_config = get_plugin_config(Config)


def should_trigger_reaction() -> bool:
    return random.random() < plugin_config.reaction_probability


# 满足概率时回复
# TODO：别人贴表情牛牛跟着贴
async def reaction_filter(bot: Bot, event: GroupMessageEvent, state: T_State):
    if not should_trigger_reaction():
        return False

    return should_trigger_reaction()


def get_random_emoji() -> str:
    return str(random.choice(EMOJI_IDS))


reaction_msg = on_message(
    rule=Rule(reaction_filter),
    priority=16,
)


@reaction_msg.handle()
async def handle_reaction(bot: Bot, event: GroupMessageEvent):
    if not plugin_config.enable_reaction:
        return

    if not should_trigger_reaction():
        logger.debug(f"[Reaction] Reaction not triggered for bot {event.self_id}")
        return

    bot_id = str(bot.self_id)
    emoji_code = get_random_emoji()
    logger.debug(f"[Reaction] Selected emoji code: {emoji_code}")

    protocol: str | None = last_successful_protocol.get(bot_id)

    if protocol:
        try:
            logger.debug(f"[Reaction] Trying cached protocol {protocol} for bot {bot_id}")
            await send_reaction(bot, event, emoji_code, protocol)
            logger.info(f"[Reaction] Successfully used cached protocol {protocol} for bot {bot_id}.")
            return
        except ActionFailed as e:
            logger.warning(f"[Reaction] Cached protocol {protocol} failed for bot {bot_id}: {str(e)}")
            del last_successful_protocol[bot_id]

    for proto in SUPPORTED_PROTOCOLS:
        try:
            logger.debug(f"[Reaction] Testing protocol {proto} for bot {bot_id}")
            await send_reaction(bot, event, emoji_code, proto)
            last_successful_protocol[bot_id] = proto
            logger.info(f"[Reaction] Detected and cached protocol {proto} for bot {bot_id}.")
            return
        except ActionFailed as e:
            logger.warning(f"[Reaction] Protocol {proto} failed for bot {bot_id}: {str(e)}")

    logger.error(f"[Reaction] No valid protocol found for bot {bot_id}.")


async def send_reaction(bot: Bot, event: Event, emoji_code: str, protocol: str) -> None:
    try:
        if protocol == "Lagrange":
            await bot.call_api(
                "set_group_reaction",
                group_id=event.group_id,
                message_id=event.message_id,
                code=emoji_code,
                is_add=True,
            )
        elif protocol == "NapCat":
            await bot.call_api(
                "set_msg_emoji_like",
                message_id=event.message_id,
                emoji_id=int(emoji_code),
            )
        logger.info(f"[Reaction] Successfully sent reaction {emoji_code} using protocol {protocol}")
    except Exception as e:
        logger.error(
            f"[Reaction] Failed to send reaction {emoji_code} using protocol {protocol}: {str(e)}", exc_info=True
        )
