from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    # 邮件推送配置
    bot_status_smtp_user: str = ""
    bot_status_smtp_password: str = ""
    bot_status_smtp_server: str = ""
    bot_status_smtp_port: int = 465
    bot_status_notice_email: str = ""
    # 离线等待时长
    bot_status_offline_grace_time: int = 30


class MailConfig:
    def __init__(self, user: str, password: str, server: str, port: int, notice_email: str):
        self.user = user
        self.password = password
        self.server = server
        self.port = port
        self.notice_email = notice_email

    def check_params(self) -> bool:
        """检查参数是否填写完整"""
        if self.user and self.password and self.server and self.port and self.notice_email:
            return True
        else:
            return False


driver = get_driver()
global_config = driver.config
plugin_config = get_plugin_config(Config)
