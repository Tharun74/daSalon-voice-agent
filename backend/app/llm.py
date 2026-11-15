import logging
import os
import re
import time
from typing import Any, List, Optional
from openai import OpenAI

from app import config

logger = logging.getLogger("dasalon.llm")

_client: Optional[OpenAI] = None


def get_llm_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.FIREWORKS_API_KEY,
            base_url="https://api.fireworks.ai/inference/v1/",
            timeout=35.0,
        )
    return _client


def clean_content(content: Optional[str]) -> str:
    """Strip reasoning tokens or <think> tags from model output."""
    if not content:
        return ""
    if '<|channel|>final<|message|>' in content:
        content = content.split('<|channel|>final<|message|>')[-1]
    elif '<|channel|>analysis' in content:
        return ''
    content = re.sub(r'<\|[^|]+\|>', '', content)
    # Strip <think>...</think>
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content)
    # Strip any trailing/leading think tags if unclosed
    cleaned = re.sub(r"<think>[\s\S]*", "", cleaned)
    return cleaned.strip()


def complete(
    messages: List[dict],
    tools: Optional[List[dict]] = None,
    temperature: float = 0.2,
    max_tokens: int = 1000,
    model: Optional[str] = None,
) -> Any:
    """
    Call Fireworks AI LLM with retry (once) and fallback.
    Returns the message object with cleaned content and optional tool_calls.
    """
    client = get_llm_client()
    target_model = model or config.LLM_MODEL

    kwargs = {
        "model": target_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if 'gpt-oss' in target_model:
        kwargs['reasoning_effort'] = 'low'
        kwargs['max_tokens'] = max(max_tokens, 2048)

    last_error = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg = choice.message

            # Clean content from any reasoning tags
            if msg.content:
                msg.content = clean_content(msg.content)

            return msg
        except Exception as e:
            last_error = e
            logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                time.sleep(1.0)

    logger.error(f"All LLM attempts failed: {last_error}")
    raise RuntimeError(f"LLM call failed after retries: {last_error}")



def complete_stream(messages, tools=None):
    """Yield visible deltas, then the same message shape as complete()."""
    from types import SimpleNamespace
    voice = any("salon's friendly receptionist on a live call" in m.get('content', '') for m in messages if m.get('role') == 'system')
    model = os.getenv('VOICE_LLM_MODEL', config.LLM_MODEL) if voice else config.LLM_MODEL
    if 'gpt-oss' in model:
        # Harmony reasoning must never enter captions/audio. Receive a parsed
        # completion before exposing visible text; speech still streams in chunks.
        message = complete(messages, tools=tools, max_tokens=2048, model=model)
        message.content = clean_content(message.content)
        if message.content and not message.tool_calls:
            yield {'type': 'assistant_text_delta', 'text': message.content}
        yield {'type': 'message', 'message': message}
        return
    kwargs = dict(model=os.getenv('VOICE_LLM_MODEL', config.LLM_MODEL) if voice else config.LLM_MODEL,
                  messages=messages, temperature=0.2, max_tokens=384 if voice else 1000, stream=True)
    if voice and 'gpt-oss' in kwargs['model']:
        kwargs['reasoning_effort'] = 'low'
    budget = SpeechBudget() if voice else None
    if tools:
        kwargs.update(tools=tools, tool_choice="auto")
    calls, content = {}, ""
    # Buffer XML reasoning so it can never enter captions or speech.
    visible, in_think, pending = "", False, ""
    with get_llm_client().chat.completions.create(**kwargs) as stream:
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            for tc in delta.tool_calls or []:
                item = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                item["id"] += tc.id or ""
                if tc.function:
                    item["name"] += tc.function.name or ""
                    item["arguments"] += tc.function.arguments or ""
            if delta.content:
                content += delta.content
                pending += delta.content
                while pending:
                    tag = "</think>" if in_think else "<think>"
                    pos = pending.find(tag)
                    if pos >= 0:
                        text = pending[:pos]
                        pending = pending[pos + len(tag):]
                        if not in_think and text:
                            if budget:
                                text = budget.feed(text)
                            visible += text
                            yield {"type": "assistant_text_delta", "text": text}
                        in_think = not in_think
                    else:
                        keep = next((n for n in range(min(len(tag)-1, len(pending)), 0, -1)
                                     if pending.endswith(tag[:n])), 0)
                        text = pending[:-keep] if keep else pending
                        pending = pending[-keep:] if keep else ""
                        if not in_think and text:
                            if budget:
                                text = budget.feed(text)
                            visible += text
                            yield {"type": "assistant_text_delta", "text": text}
                        break
    if pending and not in_think:
        if budget:
            pending = budget.feed(pending)
        yield {"type": "assistant_text_delta", "text": pending}
    tool_calls = [SimpleNamespace(id=c["id"], function=SimpleNamespace(
        name=c["name"], arguments=c["arguments"])) for _, c in sorted(calls.items())]
    yield {"type": "message", "message": SimpleNamespace(
        content=budget.text.strip() if budget else clean_content(content), tool_calls=tool_calls or None)}


class SpeechBudget:
    """Monotonic streaming cap: two sentences, 45 words, 300 characters."""
    def __init__(self):
        self.text = ''
        self.stopped = False

    def feed(self, delta):
        if self.stopped:
            return ''
        start = len(self.text)
        candidate = self.text + delta
        ends = list(re.finditer(r'[.!?।](?:\s|$)', candidate))
        boundaries = [300]
        if len(ends) >= 2:
            boundaries.append(ends[1].start() + 1)
        words = list(re.finditer(r'\S+', candidate))
        if len(words) > 45:
            boundaries.append(words[45].start())
        end = min(boundaries)
        self.text = candidate[:end]
        self.stopped = len(candidate) >= end
        return self.text[start:]
