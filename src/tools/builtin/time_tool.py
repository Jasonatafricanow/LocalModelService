from datetime import datetime

from pydantic import BaseModel, Field

from src.tools.registry import BaseTool


class TimeInput(BaseModel):
    format: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="时间格式，如 %Y-%m-%d %H:%M:%S",
    )


class TimeTool(BaseTool):
    name: str = "get_current_time"
    description: str = "获取当前日期和时间，支持自定义格式"
    args_schema: type[TimeInput] = TimeInput

    def run(self, **kwargs) -> str:
        fmt = kwargs.get("format", "%Y-%m-%d %H:%M:%S")
        return datetime.now().strftime(fmt)
