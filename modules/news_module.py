"""
新闻模块 - 每天60秒读懂世界

提供每日新闻摘要、历史上的今天、AI资讯等功能
"""

import aiohttp
import asyncio
import base64
from typing import Tuple, Any
from src.common.logger import get_logger
from src.plugin_system.base.base_tool import BaseTool, ToolParamType
from src.plugin_system.base.base_command import BaseCommand

logger = get_logger("entertainment_plugin.news")


class News60sTool(BaseTool):
    """获取60秒新闻的工具"""

    name = "get_60s_news"
    description = "获取今日热点新闻(10-15条+微语)。用户问新闻/时事时调用"
    parameters = [
        ("format", ToolParamType.STRING, "返回格式，默认为text", False, ["text", "simple"])
    ]
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """获取60秒新闻"""
        try:
            # 获取可选参数
            format_type = function_args.get("format", "text")

            api_url = self.get_config(
                "news.api_url",
                "https://60s.viki.moe/v2/60s"
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=10) as response:
                    if response.status != 200:
                        return {
                            "name": self.name,
                            "content": f"获取新闻失败，HTTP状态码: {response.status}"
                        }

                    data = await response.json()

                    # 提取新闻内容
                    if data.get("code") == 200:
                        news_data = data.get("data", {})
                        news_list = news_data.get("news", [])

                        if not news_list:
                            return {"name": self.name, "content": "暂无新闻数据"}

                        # 格式化新闻内容
                        news_text = "\n".join(
                            [f"{i+1}. {item}" for i, item in enumerate(news_list)]
                        )
                        tip = news_data.get("tip", "")

                        # 根据 format 参数决定输出格式
                        if format_type == "simple":
                            result = f"每天60秒读懂世界\n\n{news_text}"
                        else:
                            result = f"📰 每天60秒读懂世界\n\n{news_text}"
                            if tip:
                                result += f"\n\n💡 {tip}"

                        return {"name": self.name, "content": result}
                    else:
                        return {
                            "name": self.name,
                            "content": f"获取新闻失败: {data.get('message', '未知错误')}"
                        }

        except asyncio.TimeoutError:
            return {"name": self.name, "content": "获取新闻超时，请稍后再试"}
        except Exception as e:
            logger.error(f"获取60秒新闻失败: {e}", exc_info=True)
            return {"name": self.name, "content": f"获取新闻失败: {str(e)}"}


class TodayInHistoryTool(BaseTool):
    """获取历史上的今天的工具"""

    name = "get_today_in_history"
    description = "获取历史上的今天事件列表(含年份+描述)。用户问历史事件时调用"
    parameters = [
        ("limit", ToolParamType.INTEGER, "返回的事件数量，默认为10", False, None)
    ]
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """获取历史上的今天"""
        try:
            # 获取可选参数
            limit = function_args.get("limit", 10)

            api_url = self.get_config(
                "news.history_api_url",
                "https://60s.viki.moe/v2/today-in-history"
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=10) as response:
                    if response.status != 200:
                        return {
                            "name": self.name,
                            "content": f"获取历史事件失败，HTTP状态码: {response.status}"
                        }

                    data = await response.json()

                    if data.get("code") == 200:
                        # API 返回格式: {"data": {"date": "...", "items": [...]}}
                        data_obj = data.get("data", {})
                        events = data_obj.get("items", []) if isinstance(data_obj, dict) else data_obj

                        if not events:
                            return {"name": self.name, "content": "暂无历史事件数据"}

                        # 根据 limit 参数限制数量
                        events = events[:limit]

                        # 格式化历史事件
                        result = "📅 历史上的今天\n\n"
                        for event in events:
                            year = event.get("year", "")
                            title = event.get("title", "")
                            result += f"• {year}年 - {title}\n"

                        return {"name": self.name, "content": result.strip()}
                    else:
                        return {
                            "name": self.name,
                            "content": f"获取历史事件失败: {data.get('message', '未知错误')}"
                        }

        except asyncio.TimeoutError:
            return {"name": self.name, "content": "获取历史事件超时，请稍后再试"}
        except Exception as e:
            logger.error(f"获取历史上的今天失败: {e}", exc_info=True)
            return {"name": self.name, "content": f"获取历史事件失败: {str(e)}"}


class AINewsTool(BaseTool):
    """获取每日AI资讯的工具"""

    name = "get_ai_news"
    description = "获取今日AI领域新闻资讯(含标题+摘要+来源)。用户问AI/人工智能相关新闻时调用"
    parameters = [
        ("limit", ToolParamType.INTEGER, "返回的新闻数量，默认为5", False, None)
    ]
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """获取每日AI资讯"""
        try:
            limit = function_args.get("limit", 5)

            api_url = self.get_config(
                "news.ai_news_api_url",
                "https://60s.viki.moe/v2/ai-news"
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=15) as response:
                    if response.status != 200:
                        return {
                            "name": self.name,
                            "content": f"获取AI资讯失败，HTTP状态码: {response.status}"
                        }

                    data = await response.json()

                    if data.get("code") == 200:
                        news_data = data.get("data", {})
                        news_list = news_data.get("news", [])

                        if not news_list:
                            return {"name": self.name, "content": "暂无AI资讯数据"}

                        # 限制数量
                        news_list = news_list[:limit]

                        # 格式化AI资讯
                        result = "🤖 每日AI资讯\n\n"
                        for i, news in enumerate(news_list, 1):
                            title = news.get("title", "")
                            detail = news.get("detail", "")
                            source = news.get("source", "")
                            link = news.get("link", "")
                            result += f"{i}. {title}\n"
                            if detail:
                                result += f"   {detail}\n"
                            if source:
                                result += f"   来源: {source}\n"
                            if link:
                                result += f"   链接: {link}\n"
                            result += "\n"

                        return {"name": self.name, "content": result.strip()}
                    else:
                        return {
                            "name": self.name,
                            "content": f"获取AI资讯失败: {data.get('message', '未知错误')}"
                        }

        except asyncio.TimeoutError:
            return {"name": self.name, "content": "获取AI资讯超时，请稍后再试"}
        except Exception as e:
            logger.error(f"获取AI资讯失败: {e}", exc_info=True)
            return {"name": self.name, "content": f"获取AI资讯失败: {str(e)}"}


class NewsCommand(BaseCommand):
    """60秒新闻 Command - 通过命令查询新闻"""

    command_name = "news"
    command_description = "查询每天60秒读懂世界新闻"
    command_pattern = r"^/(news|新闻)$"
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行新闻查询命令"""
        try:
            api_url = self.get_config(
                "news.api_url",
                "https://60s.viki.moe/v2/60s"
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=10) as response:
                    if response.status != 200:
                        await self.send_text("获取新闻失败，请稍后再试")
                        return False, f"HTTP错误: {response.status}", True

                    data = await response.json()

                    if data.get("code") == 200:
                        news_data = data.get("data", {})
                        news_list = news_data.get("news", [])
                        tip = news_data.get("tip", "")
                        image_url = news_data.get("image", "")

                        if not news_list:
                            await self.send_text("暂时没有新闻数据")
                            return False, "无新闻数据", True

                        # 发送图片
                        if image_url and self.get_config("news.send_image", True):
                            try:
                                async with session.get(image_url, timeout=15) as img_response:
                                    if img_response.status == 200:
                                        image_data = await img_response.read()
                                        image_base64 = base64.b64encode(image_data).decode()
                                        await self.send_image(image_base64)
                            except Exception as e:
                                logger.warning(f"发送新闻图片失败: {e}")

                        # 发送文本
                        if self.get_config("news.send_text", True):
                            news_text = "\n".join(
                                [f"{i+1}. {item}" for i, item in enumerate(news_list)]
                            )
                            message = f"📰 每天60秒读懂世界\n\n{news_text}"
                            if tip:
                                message += f"\n\n💡 {tip}"

                            await self.send_text(message)

                        return True, "发送新闻成功", True
                    else:
                        await self.send_text("获取新闻失败")
                        return False, f"API错误: {data.get('message')}", True

        except Exception as e:
            logger.error(f"查询新闻失败: {e}", exc_info=True)
            await self.send_text("查询新闻时出错了")
            return False, str(e), True


class HistoryCommand(BaseCommand):
    """历史上的今天 Command"""

    command_name = "history"
    command_description = "查询历史上的今天"
    command_pattern = r"^/(history|历史)$"
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行历史查询命令"""
        try:
            api_url = self.get_config(
                "news.history_api_url",
                "https://60s.viki.moe/v2/today-in-history"
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=10) as response:
                    if response.status != 200:
                        await self.send_text("获取历史事件失败，请稍后再试")
                        return False, f"HTTP错误: {response.status}", True

                    data = await response.json()

                    if data.get("code") == 200:
                        # API 返回格式: {"data": {"date": "...", "items": [...]}}
                        data_obj = data.get("data", {})
                        events = data_obj.get("items", []) if isinstance(data_obj, dict) else data_obj

                        if not events:
                            await self.send_text("暂时没有历史事件数据")
                            return False, "无历史数据", True

                        # 限制数量
                        max_events = int(self.get_config("news.max_history_events", 10))
                        events = events[:max_events]

                        # 格式化
                        message = "📅 历史上的今天\n\n"
                        for event in events:
                            year = event.get("year", "")
                            title = event.get("title", "")
                            message += f"• {year}年 - {title}\n"

                        await self.send_text(message.strip())
                        return True, "发送历史事件成功", True
                    else:
                        await self.send_text("获取历史事件失败")
                        return False, f"API错误: {data.get('message')}", True

        except Exception as e:
            logger.error(f"查询历史事件失败: {e}", exc_info=True)
            await self.send_text("查询历史事件时出错了")
            return False, str(e), True


class AINewsCommand(BaseCommand):
    """AI资讯 Command - 通过命令查询AI新闻"""

    command_name = "ainews"
    command_description = "查询每日AI资讯"
    command_pattern = r"^/(ainews|ai新闻|AI新闻|ai资讯|AI资讯)$"
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行AI资讯查询命令"""
        try:
            api_url = self.get_config(
                "news.ai_news_api_url",
                "https://60s.viki.moe/v2/ai-news"
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=15) as response:
                    if response.status != 200:
                        await self.send_text("获取AI资讯失败，请稍后再试")
                        return False, f"HTTP错误: {response.status}", True

                    data = await response.json()

                    if data.get("code") == 200:
                        news_data = data.get("data", {})
                        news_list = news_data.get("news", [])

                        if not news_list:
                            await self.send_text("暂时没有AI资讯数据")
                            return False, "无AI资讯数据", True

                        # 限制数量
                        max_news = int(self.get_config("news.max_ai_news", 5))
                        news_list = news_list[:max_news]

                        # 格式化
                        message = "🤖 每日AI资讯\n\n"
                        for i, news in enumerate(news_list, 1):
                            title = news.get("title", "")
                            detail = news.get("detail", "")
                            source = news.get("source", "")
                            link = news.get("link", "")
                            message += f"{i}. {title}\n"
                            if detail:
                                message += f"   {detail}\n"
                            if source:
                                message += f"   来源: {source}\n"
                            if link:
                                message += f"   链接: {link}\n"
                            message += "\n"

                        await self.send_text(message.strip())
                        return True, "发送AI资讯成功", True
                    else:
                        await self.send_text("获取AI资讯失败")
                        return False, f"API错误: {data.get('message')}", True

        except Exception as e:
            logger.error(f"查询AI资讯失败: {e}", exc_info=True)
            await self.send_text("查询AI资讯时出错了")
            return False, str(e), True
