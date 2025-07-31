from urllib.parse import quote_plus

from beanie import init_beanie
from pymongo import AsyncMongoClient

from .modules import (
    Answer,
    Ban,
    BlackList,
    BotConfigModule,
    Context,
    GroupConfigModule,
    ImageCache,
    Message,
    SingProgress,
    UserConfigModule,
)


async def init_db(host: str, port: int, user: str, password: str):
    if user and password:
        connection_string = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}"
    else:
        connection_string = f"mongodb://{host}:{port}"
    mongo_client = AsyncMongoClient(connection_string, unicode_decode_error_handler="ignore")
    await init_beanie(
        database=mongo_client["PallasBot"],
        document_models=[
            BotConfigModule,
            GroupConfigModule,
            UserConfigModule,
            Message,
            Context,
            BlackList,
            ImageCache,
        ],
    )
