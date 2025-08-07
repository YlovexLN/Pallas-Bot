from pydantic import BaseModel


class Config(BaseModel, extra="ignore"):
    # 是否启用被踢自动拉黑功能
    enable_kick_ban: bool = True
