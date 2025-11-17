"""
异步 API 客户端工具

统一封装所有 HTTP 请求，提供重试、超时、错误处理等功能
"""

import aiohttp
import asyncio
import base64
from typing import Optional, Dict, Any, List
from src.common.logger import get_logger

logger = get_logger("entertainment_plugin.api_client")


class AsyncAPIClient:
    """异步 API 客户端"""

    def __init__(self, timeout: int = 10):
        """
        初始化客户端

        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout

    async def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
        base_delay: float = 1.0,
        log_prefix: str = "[API]"
    ) -> Optional[Dict[str, Any]]:
        """
        发送 GET 请求并返回 JSON 响应

        Args:
            url: 请求 URL
            params: 查询参数
            retries: 重试次数
            base_delay: 基础延迟时间（指数退避）
            log_prefix: 日志前缀

        Returns:
            JSON 响应字典，失败返回 None
        """
        for attempt in range(1, retries + 1):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as session:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"{log_prefix} 请求成功: {url}")
                            return data
                        else:
                            logger.warning(
                                f"{log_prefix} 请求失败 (尝试 {attempt}/{retries}), "
                                f"状态码: {response.status}"
                            )

            except asyncio.TimeoutError:
                logger.error(f"{log_prefix} 请求超时 (尝试 {attempt}/{retries})")
            except Exception as e:
                logger.error(
                    f"{log_prefix} 请求异常 (尝试 {attempt}/{retries}): "
                    f"{type(e).__name__}: {e}"
                )

            # 指数退避重试
            if attempt < retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.info(f"{log_prefix} 等待 {delay:.1f}秒后重试...")
                await asyncio.sleep(delay)

        logger.error(f"{log_prefix} 所有重试均失败: {url}")
        return None

    async def download_image_base64(
        self,
        url: str,
        max_size: int = 5 * 1024 * 1024,
        log_prefix: str = "[ImageDownload]"
    ) -> Optional[str]:
        """
        下载图片并转为 base64

        Args:
            url: 图片 URL
            max_size: 最大文件大小（字节）
            log_prefix: 日志前缀

        Returns:
            base64 编码的图片，失败返回 None
        """
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.warning(
                            f"{log_prefix} 下载失败，状态码: {response.status}"
                        )
                        return None

                    # 检查内容类型
                    content_type = response.headers.get('Content-Type', '')
                    if not content_type.startswith('image/'):
                        logger.warning(f"{log_prefix} 非图片类型: {content_type}")
                        return None

                    # 检查文件大小
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > max_size:
                        logger.warning(
                            f"{log_prefix} 文件过大: {int(content_length)} > {max_size}"
                        )
                        return None

                    # 读取内容
                    content = await response.read()
                    if len(content) > max_size:
                        logger.warning(
                            f"{log_prefix} 实际内容过大: {len(content)} > {max_size}"
                        )
                        return None

                    return base64.b64encode(content).decode('utf-8')

        except asyncio.TimeoutError:
            logger.warning(f"{log_prefix} 下载超时: {url[:50]}")
        except Exception as e:
            logger.warning(
                f"{log_prefix} 下载失败: {type(e).__name__}: {e}"
            )

        return None
