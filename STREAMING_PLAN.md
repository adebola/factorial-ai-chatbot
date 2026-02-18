# Streaming Chat Responses — Implementation Plan

## Goal

Replace the current all-at-once response delivery with token-by-token streaming via WebSocket. Users see text appear progressively (~50ms per token) instead of waiting 1.5-2.5s for the full response. No functional changes — same RAG pipeline, same quality, just faster perceived latency.

---

## Current Flow

```
User message → RAG search → OpenAI (wait for full response) → WebSocket send → Widget renders all at once
```

## Target Flow

```
User message → RAG search → OpenAI stream → WebSocket chunks → Widget renders progressively
```

---

## WebSocket Protocol Changes

### New Message Types

```javascript
// Stream start — tells widget to create a new message bubble
{
    "type": "stream_start",
    "session_id": "uuid",
    "timestamp": "2026-02-13T..."
}

// Stream chunk — append text to the current message bubble
{
    "type": "stream_chunk",
    "delta": "partial text token"
}

// Stream end — finalize the message, include metadata for feedback/sources
{
    "type": "stream_end",
    "content": "full accumulated text",   // For clients that missed chunks
    "message_id": "uuid",
    "session_id": "uuid",
    "sources": [...],
    "metadata": {...},
    "quality_metrics": {...},
    "timestamp": "2026-02-13T..."
}
```

### Backward Compatibility

Workflow responses (choices, input prompts) continue using the existing `{"type": "message"}` format unchanged. Streaming only applies to AI-generated text responses.

---

## Backend Changes

### File 1: `chat-service/app/services/chat_service.py`

**Add `generate_response_streaming()` method** — a generator version of `generate_response()`.

```python
async def generate_response_streaming(
    self,
    tenant_id: str,
    user_message: str,
    session_id: str,
    tenant: Dict = None,
    pre_search_result: Dict = None
):
    """
    Stream AI response tokens. Yields (chunk_type, data) tuples.

    Yields:
        ("start", {})                     — Stream beginning
        ("chunk", {"delta": "token"})     — Each token
        ("end", {"content": "...", ...})  — Final message with metadata
    """
    # Same RAG setup as generate_response() — tenant lookup, vector search,
    # history fetch (or use pre_search_result)
    # ...build messages array same as before...

    # Key change: use stream=True
    response_stream = self.openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=1500,
        timeout=30.0,
        stream=True  # <-- This is the only OpenAI API change
    )

    yield ("start", {})

    full_content = []
    for chunk in response_stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_content.append(delta)
            yield ("chunk", {"delta": delta})

    response_content = "".join(full_content)

    # Same post-processing: store history, compute quality metrics
    self._store_conversation_turn(session_id, user_message, response_content)

    # ... compute quality_metrics, sources, etc same as current code ...

    yield ("end", {
        "content": response_content,
        "sources": sources,
        "metadata": {...},
        "quality_metrics": quality_metrics
    })
```

**Important**: The sync OpenAI client's `stream=True` returns a synchronous iterator. Since `chat.py` is async, wrap iteration in `run_in_executor` or use a queue pattern:

```python
# Option A: Use asyncio.Queue as bridge between sync iterator and async consumer
async def generate_response_streaming(self, ...):
    # ... setup code (same as generate_response) ...

    queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _stream_to_queue():
        """Run in thread pool — iterates sync OpenAI stream, puts chunks in async queue."""
        try:
            response_stream = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=1500,
                timeout=30.0,
                stream=True
            )
            for chunk in response_stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    loop.call_soon_threadsafe(queue.put_nowait, ("chunk", delta))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))

    # Start streaming in thread pool
    stream_future = loop.run_in_executor(None, _stream_to_queue)

    yield ("start", {})

    full_content = []
    while True:
        msg_type, data = await queue.get()
        if msg_type == "chunk":
            full_content.append(data)
            yield ("chunk", {"delta": data})
        elif msg_type == "done":
            break
        elif msg_type == "error":
            raise Exception(data)

    await stream_future  # Ensure thread cleanup

    response_content = "".join(full_content)
    # ... post-processing same as current ...
    yield ("end", {...})
```

**Keep `generate_response()` unchanged** — it's still used for workflow fallback paths where streaming doesn't apply.

### File 2: `chat-service/app/websockets/chat.py`

In the AI response path (where `timing_path = "ai"`), replace:

```python
# BEFORE:
ai_response = await self.chat_service.generate_response(...)

# AFTER:
async for chunk_type, chunk_data in self.chat_service.generate_response_streaming(
    tenant_id=tenant_id,
    user_message=user_message,
    session_id=session_id,
    tenant=tenant,
    pre_search_result=pre_search_result  # from parallelized path if available
):
    if chunk_type == "start":
        await websocket.send_text(json.dumps({
            "type": "stream_start",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }))
    elif chunk_type == "chunk":
        await websocket.send_text(json.dumps({
            "type": "stream_chunk",
            "delta": chunk_data["delta"]
        }))
    elif chunk_type == "end":
        ai_response = chunk_data  # Contains content, sources, metadata, quality_metrics
        await websocket.send_text(json.dumps({
            "type": "stream_end",
            "content": ai_response["content"],
            "message_id": ...,   # from DB record created below
            "session_id": session_id,
            "sources": ai_response.get("sources", []),
            "metadata": ai_response.get("metadata", {}),
            "timestamp": datetime.now().isoformat()
        }))
```

The DB write (ChatMessage) and event publishing happen after `stream_end`, same as today. The `stream_end` message includes `message_id` so the widget can attach feedback buttons.

**Workflow paths remain unchanged** — they still use `{"type": "message"}` since workflow responses are short and not streamed from OpenAI.

---

## Frontend/Widget Changes

### File 3: `onboarding-service/app/services/widget_service.py`

The chat widget JavaScript is generated in this file (~lines 870-1012). Changes needed:

#### 3a. WebSocket `onmessage` handler (~line 877)

Add handling for the three new message types:

```javascript
this.socket.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'stream_start') {
        // Create an empty message bubble with a reference we can append to
        this.hideTypingIndicator();
        this.currentStreamEl = this.addStreamingMessage();

    } else if (data.type === 'stream_chunk') {
        // Append token to the current streaming message
        if (this.currentStreamEl) {
            this.currentStreamEl.textContent += data.delta;
            this.scrollToBottom();
        }

    } else if (data.type === 'stream_end') {
        // Finalize: set full content (safety), add feedback buttons, add sources
        if (this.currentStreamEl) {
            this.currentStreamEl.textContent = data.content;
        }
        this.finalizeStreamingMessage(data.message_id, data.sources, data.metadata);
        this.currentStreamEl = null;
        this.enableSendButton();

    } else if (data.type === 'message' && data.role === 'assistant') {
        // Non-streamed messages (workflow responses) — existing behavior
        // ... unchanged ...

    } else if (data.type === 'connection') {
        // ... unchanged ...
    } else if (data.type === 'error') {
        // ... unchanged ...
    }
};
```

#### 3b. New widget methods

```javascript
addStreamingMessage() {
    // Create message bubble (same DOM structure as addMessage)
    // but WITHOUT content yet. Return the content div element.
    const wrapper = document.createElement('div');
    wrapper.className = 'cc-message cc-bot-message';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'cc-message-content cc-bot-content';
    wrapper.appendChild(contentDiv);

    this.messagesContainer.appendChild(wrapper);
    this.scrollToBottom();

    // Store wrapper reference for later finalization
    this._streamingWrapper = wrapper;
    return contentDiv;
}

finalizeStreamingMessage(messageId, sources, metadata) {
    if (!this._streamingWrapper) return;

    // Add feedback buttons (same as existing addMessage logic)
    if (messageId) {
        const feedbackDiv = this.createFeedbackButtons(messageId);
        this._streamingWrapper.appendChild(feedbackDiv);
    }

    // Handle choices if present (workflow hybrid path)
    if (metadata && metadata.choices && metadata.choices.length > 0) {
        this.addChoices(metadata.choices);
    }

    this._streamingWrapper = null;
    this.scrollToBottom();
}
```

#### 3c. CSS addition

Add a blinking cursor animation during streaming:

```css
.cc-message-content.cc-streaming::after {
    content: '|';
    animation: cc-blink 0.7s infinite;
}

@keyframes cc-blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
}
```

Apply `cc-streaming` class in `addStreamingMessage()`, remove it in `finalizeStreamingMessage()`.

---

## Angular Admin Chat Monitoring

### File 4: `frontend/chatcraft-superadmin/src/app/features/chat-monitoring/chat-detail-dialog.component.ts`

The super-admin chat monitoring dialog displays historical chat messages. **No changes needed** — it reads completed messages from the API, not live WebSocket streams. The `stream_end` message's `content` field ensures the full message is stored in the DB as before.

---

## Edge Cases

1. **WebSocket disconnect during stream** — Client reconnects and misses chunks. The `stream_end.content` field contains the full text, so a reconnecting client can recover. But mid-stream disconnects mean the user sees a partial message. Consider: on reconnect, fetch the last message from REST API.

2. **Workflow fallback during stream** — Not applicable. Streaming only starts after we've confirmed we're on the AI path (workflow check already completed).

3. **Error during stream** — If OpenAI errors mid-stream, send:
   ```json
   {"type": "stream_end", "content": "[partial content so far]", "error": "Generation interrupted"}
   ```
   Still save whatever was generated to the DB.

4. **Empty stream** — If OpenAI returns no tokens, send `stream_start` → `stream_end` with empty content. Widget hides empty bubbles (existing behavior).

5. **Multiple concurrent streams** — Not possible per WebSocket connection. Each session processes one message at a time (the `while True` loop awaits each message sequentially).

---

## Files Modified (Summary)

| File | Change |
|---|---|
| `chat-service/app/services/chat_service.py` | Add `generate_response_streaming()` async generator |
| `chat-service/app/websockets/chat.py` | Use streaming generator in AI response path |
| `onboarding-service/app/services/widget_service.py` | Handle `stream_start/chunk/end` in JS, add streaming DOM methods, CSS cursor |

## Testing

1. Open widget, send message — verify tokens appear progressively
2. Send message that triggers workflow — verify workflow responses still come as single `message` type
3. Disconnect WiFi mid-stream, reconnect — verify widget recovers gracefully
4. Send very long message that produces ~1500 tokens — verify all tokens arrive and `stream_end.content` matches accumulated chunks
5. Test with `has_workflows=false` path — streaming should work on the fast AI path
6. Test with `has_workflows=true` + no trigger — streaming should work with pre_search parallelization
