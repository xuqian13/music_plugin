"""
AI绘图工具 - AI Draw Tool (统一版本)

整合主动画图和自动配图功能，供LLM智能调用
"""

import urllib.parse
import aiohttp
from typing import Tuple, Dict, Any
from src.common.logger import get_logger
from src.plugin_system.base.base_tool import BaseTool
from src.plugin_system.base.component_types import ToolParamType
from src.config.config import global_config
from src.plugin_system.apis import send_api

logger = get_logger("entertainment_plugin.ai_draw_tool")


class AIDrawTool(BaseTool):
    """
    统一的AI绘图工具 - 支持主动画图和自动配图

    使用场景：
    1. 主动画图：用户要求"画图"、"画个xxx"、"来张xxx"
    2. 自动配图：bot回复中描述了场景，需要配图增强表现力
    3. 换风格：用户说"换个风格"、"再来一张"
    """

    name = "ai_draw_tool"
    description = """智能AI绘图工具，支持三种使用场景：
1. 主动绘图：用户要求画图、绘图、生成图片时
2. 自动配图：当你的回复中描述了场景、动作或状态时，主动调用为回复配图
3. 换风格：用户说"换个风格"、"再来一张"时，发送之前缓存的其他风格图片

示例场景：
- 用户："画个小雪" → prompt="self", auto_scene=False
- 你回复："刚拍完毛线球缠住爪子的蠢样子" → prompt="", auto_scene=True, scene_description="毛线球 缠住爪子 可爱"
- 用户："换个风格" → change_style=True"""

    parameters = [
        ("prompt", ToolParamType.STRING, "图片描述词。如'猫娘'、'风景'、'jk少女'。用户要求画'你自己'/'小雪'时填'self'。自动配图时可为空。", False, None),
        ("auto_scene", ToolParamType.BOOLEAN, "是否自动配图模式。当你的回复描述了场景需要配图时设为true。主动画图时设为false。", False, None),
        ("scene_description", ToolParamType.STRING, "场景描述关键词（仅auto_scene=true时使用）。从你的回复中提取，如'毛线球 缠住爪子 可爱 猫娘'", False, None),
        ("change_style", ToolParamType.BOOLEAN, "是否切换风格。用户说'换个风格'、'再来一张'、'下一张'时设为true", False, None)
    ]

    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行AI绘图"""
        try:
            # 获取参数
            prompt = function_args.get("prompt", "").strip()
            auto_scene = function_args.get("auto_scene", False)
            scene_description = function_args.get("scene_description", "").strip()
            change_style = function_args.get("change_style", False)

            logger.info(
                f"AI绘图请求 - prompt:{prompt}, auto_scene:{auto_scene}, "
                f"scene_desc:{scene_description}, change_style:{change_style}"
            )

            # 场景1: 换风格
            if change_style:
                return await self._handle_change_style()

            # 场景2: 自动配图
            if auto_scene:
                return await self._handle_auto_scene(scene_description)

            # 场景3: 主动画图
            return await self._handle_draw(prompt)

        except Exception as e:
            logger.error(f"AI绘图失败: {e}", exc_info=True)
            return {
                "name": self.name,
                "content": f"绘图失败: {e}"
            }

    async def _handle_change_style(self) -> dict[str, Any]:
        """处理换风格请求"""
        from .ai_draw_module import get_next_unsent_image, get_cached_images

        next_image = await get_next_unsent_image(self.chat_id)
        if next_image:
            img_data, idx = next_image
            img_url = img_data.get("url")
            if img_url:
                # Tool应该使用SendAPI发送消息
                if self.chat_stream:
                    await send_api.custom_to_stream("imageurl", img_url, self.chat_stream.stream_id)

                creation_prompt = img_data.get("creation_prompt", "")
                cache = await get_cached_images(self.chat_id)
                total = len(cache["images"]) if cache else 0
                sent_count = len(cache["sent_indices"]) if cache else 0

                logger.info(
                    f"换风格成功 [{sent_count}/{total}] "
                    f"创作提示: {creation_prompt[:50]}..."
                )
                remaining = total - sent_count
                return {
                    "name": self.name,
                    "content": f"换风格成功，发送第{sent_count}张图片，还剩{remaining}张可换"
                }

        # 缓存中没有更多图片
        cache = await get_cached_images(self.chat_id)
        if cache:
            logger.info("缓存图片已全部发送")
            return {
                "name": self.name,
                "content": "之前的图都发完啦，可以重新画一批~"
            }
        else:
            logger.info("没有缓存图片")
            return {
                "name": self.name,
                "content": "没有最近的绘图记录哦，先画一张吧~"
            }

    async def _handle_auto_scene(self, scene_description: str) -> dict[str, Any]:
        """处理自动配图请求"""
        if not scene_description:
            logger.warning("自动配图缺少场景描述")
            return {
                "name": self.name,
                "content": "自动配图需要提供场景描述"
            }

        # 构建完整描述词
        bot_personality = global_config.personality.personality
        base_prompt = self.get_config("ai_draw.self_prompt", "")

        if not base_prompt:
            base_prompt = "猫娘 猫耳 白发 日系二次元 插画风格 少女 可爱 萌"
            if "猫娘" in bot_personality or "猫" in bot_personality:
                base_prompt = f"猫娘 猫耳 白发 {base_prompt}"

        # 组合人设 + 场景描述
        full_prompt = f"{base_prompt} {scene_description}"
        logger.info(f"自动配图描述词: {full_prompt}")

        return await self._call_api_and_send(full_prompt, is_auto_scene=True)

    async def _handle_draw(self, prompt: str) -> dict[str, Any]:
        """处理主动画图请求"""
        # 处理人设描述词
        if prompt.lower() in ["self", "自己", "你自己", "你"]:
            bot_personality = global_config.personality.personality
            self_prompt = self.get_config("ai_draw.self_prompt", "")

            if not self_prompt:
                self_prompt = "日系二次元 插画风格 少女 可爱 萌"
                if "猫娘" in bot_personality or "猫" in bot_personality:
                    self_prompt = f"猫娘 猫耳 白发 {self_prompt}"

            prompt = self_prompt
            logger.info(f"使用人设描述词: {prompt}")

        # 使用默认描述词
        if not prompt:
            prompt = self.get_config("ai_draw.default_prompt", "jk")
            logger.info(f"使用默认描述词: {prompt}")

        return await self._call_api_and_send(prompt, is_auto_scene=False)

    async def _call_api_and_send(self, prompt: str, is_auto_scene: bool = False) -> dict[str, Any]:
        """调用API并发送图片"""
        # 获取配置
        api_url = self.get_config("ai_draw.api_url", "https://api.xingzhige.com/API/DrawOne/")
        timeout = self.get_config("ai_draw.timeout", 30)
        selection_mode = self.get_config("ai_draw.selection_mode", "best")

        # 构建API URL
        encoded_prompt = urllib.parse.quote(prompt)
        full_api_url = f"{api_url}?prompt={encoded_prompt}"

        logger.info(f"调用API，描述词: {prompt}")

        # 调用API
        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout, connect=10, sock_read=timeout)
            async with aiohttp.ClientSession() as session:
                async with session.get(full_api_url, timeout=timeout_obj) as response:
                    if response.status != 200:
                        raise Exception(f"API请求失败，状态码: {response.status}")

                    data = await response.json()

                    if data.get("code") != 200:
                        raise Exception(f"API返回错误: {data.get('msg', '未知错误')}")

                    images = data.get("data", [])
                    if not images:
                        raise Exception("API返回的图片列表为空")

                    logger.info(f"API返回 {len(images)} 张图片")

                    # 选择最佳图片（使用优化的算法）
                    from .ai_draw_module import select_best_image, cache_images
                    selected_images, selected_idx = select_best_image(prompt, images, selection_mode)

                    if not selected_images:
                        raise Exception("未能选择到有效图片")

                    # 缓存所有图片（用于换风格功能）
                    await cache_images(self.chat_id, images, prompt, selected_idx)

                    # 发送图片
                    img_url = selected_images[0].get("url")
                    if img_url:
                        # Tool应该使用SendAPI发送消息
                        if self.chat_stream:
                            await send_api.custom_to_stream("imageurl", img_url, self.chat_stream.stream_id)

                        creation_prompt = selected_images[0].get("creation_prompt", "")

                        logger.info(
                            f"{'自动配图' if is_auto_scene else '主动画图'}成功 "
                            f"创作提示: {creation_prompt[:50]}..."
                        )

                        remaining = len(images) - 1 if selection_mode == "best" else 0
                        if remaining > 0:
                            logger.info(f"还有{remaining}张其他风格可用")

                        result_msg = f"{'配图' if is_auto_scene else '绘图'}成功 (描述: {prompt})"
                        if remaining > 0 and not is_auto_scene:
                            result_msg += f"，还有{remaining}张其他风格可换"

                        return {
                            "name": self.name,
                            "content": result_msg
                        }
                    else:
                        raise Exception("图片URL为空")

        except aiohttp.ClientError as e:
            logger.error(f"网络请求错误: {e}")
            return {
                "name": self.name,
                "content": f"网络请求失败: {e}"
            }
        except Exception as e:
            logger.error(f"API调用失败: {e}")
            return {
                "name": self.name,
                "content": f"API调用失败: {e}"
            }
