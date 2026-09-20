# WhatsApp AI Customer Service Module

WhatsApp AI 客服模块，支持自动回复客户消息、意图识别、商品目录查询和 RAG 知识库问答。

## 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| handler.py | ✅ 完成 | 主入口，处理 WhatsApp 消息收发 |
| intents.py | ✅ 完成 | 意图识别（查询/下单/售后等）|
| vision.py | ✅ 完成 | 图片识别 |
| knowledge_base.py | ✅ 完成 | RAG 知识库 |
| business_ops.py | ✅ 完成 | 业务操作（订单查询等）|
| whatsapp_bridge.py | ✅ 完成 | WhatsApp API 桥接层 |
| gpu_detector.py | ⚡ 外部 | 位于 src/gpu/ 目录 |

## 启动方式

`ash
python src/main.py
pip install -r requirements.txt
`

## 目录结构

modules/whatsapp_cs/
├── __init__.py
├── handler.py
├── intents.py
├── vision.py
├── knowledge_base.py
├── business_ops.py
├── whatsapp_bridge.py
└── templates/
    ├── pt.json
    └── en.json
