from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: str = Field(default="default", description="会话 ID")


class ChatResponse(BaseModel):
    status: str = "ok"
    session_id: str = ""
    response: str = ""
    model: str = ""


class ChatCompletionMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str = "user"
    content: str | list[dict] | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = Field(default="qwen2.5", description="模型名称")
    messages: list[ChatCompletionMessage] = Field(
        ..., min_length=1, description="消息列表"
    )
    stream: bool = Field(default=False, description="是否流式输出")
    temperature: float | None = None
    max_tokens: int | None = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionMessage | None = None
    delta: ChatCompletionMessage | None = None
    finish_reason: str | None = None


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = ""
    object: str = "chat.completion"
    model: str = ""
    choices: list[ChatCompletionChoice] = []
    usage: ChatCompletionUsage = ChatCompletionUsage()


class ToolInvokeRequest(BaseModel):
    arguments: dict = Field(default_factory=dict, description="工具参数")


class ToolInfo(BaseModel):
    name: str
    description: str
