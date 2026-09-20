# 自定义模块开发

将 `.py` 文件放入此目录，框架会自动加载并注册其中继承 `BaseTool` 的工具类。

## 示例

```python
# modules/hello_tool.py
from pydantic import BaseModel, Field
from tools.registry import BaseTool, registry


class HelloInput(BaseModel):
    name: str = Field(description="你的名字")


class HelloTool(BaseTool):
    name: str = "say_hello"
    description: str = "向用户打招呼"
    args_schema: type[HelloInput] = HelloInput

    def run(self, **kwargs) -> str:
        name = kwargs.get("name", "世界")
        return f"你好，{name}！"


registry.register(HelloTool())
```

保存后重启服务即可使用。
