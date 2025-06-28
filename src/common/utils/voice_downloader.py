import zipfile
from pathlib import Path

import httpx
from nonebot import logger

VOICES_URLS = {
    "hf-mirror": "https://hf-mirror.com/pallasbot/Pallas-Bot/resolve/main/voices/Pallas.zip",
    "huggingface": "https://huggingface.co/pallasbot/Pallas-Bot/resolve/main/voices/Pallas.zip",
}

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
RESOURCE_DIR = PROJECT_ROOT / "resource"
VOICES_DIR = RESOURCE_DIR / "voices"
TEMP_ZIP_PATH = RESOURCE_DIR / "voices_temp.zip"

VOICES = {
    "任命助理",
    "交谈1",
    "交谈2",
    "交谈3",
    "晋升后交谈1",
    "晋升后交谈2",
    "信赖提升后交谈1",
    "信赖提升后交谈2",
    "信赖提升后交谈3",
    "闲置",
    "干员报到",
    "精英化晋升1",
    "精英化晋升2",
    "编入队伍",
    "任命队长",
    "戳一下",
    "信赖触摸",
    "问候",
}


async def download_voices() -> bool:
    try:
        logger.info("开始下载语音文件...")

        # 确保目录存在
        RESOURCE_DIR.mkdir(exist_ok=True)
        VOICES_DIR.mkdir(exist_ok=True)

        # 尝试从多个源下载
        timeout = httpx.Timeout(300.0)
        limits = httpx.Limits(max_keepalive_connections=1, max_connections=1)
        download_success = False
        for source, url in VOICES_URLS.items():
            try:
                logger.info(f"尝试从 {source} 下载")
                async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                    TEMP_ZIP_PATH.write_bytes(response.content)
                    logger.info(f"下载完成，文件大小: {len(response.content) / 1024 / 1024:.2f} MB，开始解压...")
                    download_success = True
                    break

            except (httpx.HTTPStatusError, httpx.RequestError, Exception) as e:
                logger.warning(f"尝试从 {source} 下载失败: {e}")
                continue

        if not download_success:
            logger.error("语音文件下载失败")
            raise

        # 解压文件
        with zipfile.ZipFile(TEMP_ZIP_PATH, "r") as zip_ref:
            zip_ref.extractall(VOICES_DIR)

        # 删除临时压缩包
        TEMP_ZIP_PATH.unlink()

        logger.info("语音文件下载解压完成")
        return True

    except Exception as e:
        logger.error(f"下载语音文件时发生错误: {e}")
        # 清理临时文件
        if TEMP_ZIP_PATH.exists():
            try:
                TEMP_ZIP_PATH.unlink()
            except Exception:
                pass
        return False


async def ensure_voices() -> bool:
    try:
        # 检查语音文件是否存在
        pallas_dir = VOICES_DIR / "Pallas"
        if pallas_dir.exists():
            if all((pallas_dir / f"{file}.wav").exists() for file in VOICES):
                return True

        logger.info("检测到语音文件缺失，开始下载...")
        return await download_voices()

    except Exception as e:
        logger.error(f"检查语音文件时发生错误: {e}")
        return False
