# Knowledge Base — LojaTech Customer Service

Drop your training scripts, policy documents, and reference materials
here. The system loads them automatically on startup and uses them as
context when generating LLM responses.

## How to Add Content

Simply place ``.md`` or ``.txt`` files in this directory. No
configuration changes are needed — the knowledge base reloads on next
startup.

For structured Q&A content, use ``##`` markdown headings to separate
topics. Each heading is treated as a separate retrievable passage.

## Expected Format

### Portuguese (Recomendado)

```markdown
## Política de Devolução

P: Qual é o prazo para devolução?
R: O prazo para devolução é de 30 dias a partir do recebimento do produto.

## Garantia

P: Como acionar a garantia?
R: Entre em contato pelo WhatsApp com o número do pedido e a descrição
do problema. O prazo máximo é de 90 dias.
```

### English

```markdown
## Return Policy

Q: What is the return period?
A: The return period is 30 days from product receipt.

## Warranty

Q: How do I activate the warranty?
A: Contact us via WhatsApp with your order number and problem
description. Maximum term is 90 days.
```

### JSON Format (alternative)

```json
[
    {"question": "Qual o prazo de entrega?", "answer": "5 a 10 dias úteis"},
    {"question": "Quais formas de pagamento?", "answer": "Cartão de crédito, boleto e Pix"}
]
```

## Tips

- Write in Portuguese (PT-BR) for best results with your customers.
- Keep each Q&A section focused on a single topic.
- Use plain language — no markdown formatting needed inside answers.
- Files are loaded alphabetically; add a numeric prefix if order matters
  (e.g. ``01-returns.md``, ``02-warranty.md``).
