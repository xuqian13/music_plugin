"""
图片模块 - 看看腿功能

调用随机图片 API 获取腿部图片并发送给用户
"""

import random
from typing import Tuple
from src.common.logger import get_logger
from src.plugin_system.base.base_action import BaseAction, ActionActivationType
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import ChatMode

logger = get_logger("entertainment_plugin.image")


class RandomImageAction(BaseAction):
    """随机图片 Action 组件 - 智能图片获取"""

    action_name = "random_image_action"
    action_description = "获取随机腿部图片并发送"

    # 激活设置
    activation_type = ActionActivationType.KEYWORD
    mode_enable = ChatMode.ALL
    parallel_action = False

    # 关键词激活
    activation_keywords = ["看看腿", "腿", "看腿", "康康腿", "看看大长腿", "大长腿"]
    keyword_case_sensitive = False

    # Action 参数
    action_parameters = {
        "request_type": "图片请求类型，默认为腿部图片"
    }
    action_require = [
        "当用户要求看腿部图片时使用",
        "当用户说'看看腿'、'康康腿'等时使用",
        "当需要发送腿部图片时使用"
    ]
    associated_types = ["image"]

    async def execute(self) -> Tuple[bool, str]:
        """执行看看腿图片获取"""
        try:
            # 从配置获取设置
            base_url = self.get_config(
                "image.api_url",
                "https://www.onexiaolaji.cn/RandomPicture/api/"
            )
            api_key = self.get_config("image.api_key", "qq249663924")
            available_classes = self.get_config(
                "image.available_classes",
                [101, 102, 103, 104]
            )

            # 随机选择一个 class
            random_class = random.choice(available_classes)
            api_url = f"{base_url}?key={api_key}&class={random_class}"

            logger.info(
                f"{self.log_prefix} 开始获取腿部图片，使用 class={random_class}"
            )

            # 直接发送图片 API URL
            await self.send_custom("imageurl", api_url)
            logger.info(
                f"{self.log_prefix} 腿部图片发送成功 (class={random_class})"
            )
            return True, f"成功获取并发送腿部图片 (类型{random_class})"

        except Exception as e:
            logger.error(f"{self.log_prefix} 看看腿图片获取出错: {e}")
            await self.send_text(f"❌ 图片获取出错: {e}")
            return False, f"图片获取出错: {e}"


class RandomImageCommand(BaseCommand):
    """随机图片 Command - 手动图片获取命令"""

    command_name = "random_image_command"
    command_description = "获取随机腿部图片，支持指定类型"

    # 命令匹配模式：/kankan [class] 或 /看腿 [class]
    command_pattern = r"^/(kankan|看腿)(?:\s+(?P<class_param>\d+))?$"
    command_help = "获取随机腿部图片。用法：/kankan [类型] 或 /看腿 [类型]，类型可选任意数字"
    command_examples = [
        "/kankan",
        "/kankan 101",
        "/kankan 999",
        "/看腿",
        "/看腿 102"
    ]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行看看腿命令"""
        try:
            # 从配置获取设置
            base_url = self.get_config(
                "image.api_url",
                "https://www.onexiaolaji.cn/RandomPicture/api/"
            )
            api_key = self.get_config("image.api_key", "qq249663924")
            available_classes = self.get_config(
                "image.available_classes",
                [101, 102, 103, 104]
            )

            # 解析命令参数（使用 matched_groups 获取正则匹配结果）
            specified_class = self.matched_groups.get("class_param")

            if specified_class:
                # 用户指定了 class，直接使用（不做限制）
                selected_class = int(specified_class)
                logger.info(f"用户指定 class={selected_class}")
            else:
                # 用户未指定 class，随机选择
                selected_class = random.choice(available_classes)
                logger.info(f"随机选择 class={selected_class}")

            api_url = f"{base_url}?key={api_key}&class={selected_class}"
            logger.info(f"执行看看腿命令，使用 class={selected_class}")

            # 直接发送图片 API URL
            await self.send_custom("imageurl", api_url)
            return True, f"成功获取并发送腿部图片 (类型{selected_class})", True

        except Exception as e:
            logger.error(f"看看腿命令执行出错: {e}")
            await self.send_text(f"❌ 图片获取出错: {e}")
            return False, f"图片获取出错: {e}", True
