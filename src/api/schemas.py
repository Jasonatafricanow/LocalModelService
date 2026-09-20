from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: str = Field(default="default", description="会话 ID")


class ChatResponse(BaseModel):
    status: str = "ok"
    session_id: str = ""
    response: str = ""
    model: str = ""


class ChatCompletionMessage(BaseModel):
    role: str = "user"
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="qwen2.5", description="模型名称")
    messages: list[ChatCompletionMessage] = Field(
        ..., description="消息列表"
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
