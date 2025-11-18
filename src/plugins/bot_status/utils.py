from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import httpx
from nonebot import logger

from .config import MailConfig

HTTP_TIME_OUT = 10  # 请求超时，秒


class AsHttpReq:
    """httpx 异步请求封装"""

    @staticmethod
    async def get(url, **kwargs):
        proxy = None
        async with httpx.AsyncClient(proxy=proxy) as client:
            response = await client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
            return response

    @staticmethod
    async def post(url, **kwargs):
        proxy = None
        async with httpx.AsyncClient(proxy=proxy) as client:
            response = await client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
            return response


async def send_mail(title: str, content: str, mail_config: MailConfig):
    """发送邮件通知"""
    # 构造邮件内容
    message = MIMEMultipart("alternative")
    message["Subject"] = Header(title, "utf-8").encode()
    message["From"] = mail_config.user
    message["To"] = mail_config.notice_email
    message.attach(MIMEText(content))

    # 连接SMTP服务器并发送邮件
    use_tls = False
    if mail_config.port == 465:
        use_tls = True

    try:
        async with aiosmtplib.SMTP(hostname=mail_config.server, port=mail_config.port, use_tls=use_tls) as smtp:
            await smtp.login(mail_config.user, mail_config.password)
            await smtp.send_message(message)
    except Exception as e:
        err = f"邮件发送失败，错误信息如下{e}"
        logger.error(err)
        return err

    logger.info("通知邮件发送成功!")
    return None
