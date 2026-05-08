"""
Mobilerun Portal Bridge Server
- WebSocket endpoint for Android phone (reverse connection)
- MCP tools via FastMCP, SSE at /mcp/sse
- HTTP control endpoints
- Vision analysis via Doubao (volcengine ark)
- Screenshot compression via Pillow
- Deploy on Zeabur, port 8080

Confirmed working Portal methods:
  state           - get accessibility tree + phone state
  screenshot      - take screenshot (binary or base64)
  tap             - tap at coordinates
  swipe           - swipe gesture
  keyboard/key    - press key by key_code (3=HOME, 4=BACK, 66=ENTER, 67=BACKSPACE)
  keyboard/input  - input text (base64_text + clear)
  packages        - get installed app list
  launchApp       - launch app by package name
"""

import asyncio
import base64
import io
import json
import uuid
import logging

from PIL import Image
from volcenginesdkarkruntime import AsyncArk
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport

# ─────────────────────────── logging ───────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ─────────────────────────── global state ──────────────────────

phone_ws = None
pending = {}
_lock = asyncio.Lock()

_vision_client = AsyncArk()  # reads ARK_API_KEY from env

# ─────────────────────────── app & mcp ─────────────────────────

app = FastAPI(title="Mobilerun Portal Bridge")
mcp = FastMCP(
    name="mobilerun-portal",
    instructions="Control an Android phone via the Mobilerun Portal App reverse WebSocket connection.",
)

# ─────────────────────────── startup / shutdown ────────────────

@app.on_event("startup")
async def on_startup():
    log.info("Server starting up...")

@app.on_event("shutdown")
async def on_shutdown():
    log.info("Server shutting down...")
    await _cleanup_phone()

# ─────────────────────────── core helpers ──────────────────────

async def _cleanup_phone():
    global phone_ws
    phone_ws = None
    for fut in list(pending.values()):
        if not fut.done():
            fut.set_exception(ConnectionError("Phone disconnected"))
    pending.clear()
    log.warning("Phone disconnected - pending requests cancelled.")


async def send_command(method, params=None, timeout=10.0):
    global phone_ws
    if phone_ws is None:
        raise RuntimeError("No phone connected")

    cid = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    pending[cid] = fut

    payload = json.dumps({"id": cid, "method": method, "params": params or {}})
    try:
        async with _lock:
            await phone_ws.send_text(payload)
        result = await asyncio.wait_for(fut, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        raise TimeoutError("Command '{}' timed out after {}s".format(method, timeout))
    finally:
        pending.pop(cid, None)


def compress_screenshot(b64, max_width=720, quality=60):
    """Resize and compress a base64 PNG to a smaller base64 JPEG."""
    try:
        img_bytes = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_bytes))
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        log.warning("Image compression failed: %s, returning original", e)
        return b64


async def _screenshot_internal():
    """内部截图函数，不暴露为MCP工具。"""
    resp = await send_command("screenshot", {}, timeout=15.0)
    b64 = resp.get("result", "")
    if not b64:
        return ""
    return compress_screenshot(b64)


def parse_nodes(tree, text_filter="", class_filter="", clickable_only=False):
    """递归遍历 Portal 无障碍树，提取节点列表。"""
    matches = []

    def walk(node):
        if not isinstance(node, dict):
            return
        node_text = node.get("text", "") or node.get("contentDescription", "") or ""
        node_class = node.get("className", "") or ""
        is_clickable = node.get("isClickable", False)
        bounds = node.get("boundsInScreen", None)

        text_match = (not text_filter) or (text_filter.lower() in node_text.lower())
        class_match = (not class_filter) or (class_filter.lower() in node_class.lower())
        click_match = (not clickable_only) or is_clickable

        if text_match and class_match and click_match and bounds:
            left = bounds.get("left", 0)
            top = bounds.get("top", 0)
            right = bounds.get("right", 0)
            bottom = bounds.get("bottom", 0)
            if right > left and bottom > top:
                matches.append({
                    "text": node_text,
                    "class": node_class,
                    "clickable": is_clickable,
                    "editable": node.get("isEditable", False),
                    "bounds": bounds,
                    "center_x": (left + right) // 2,
                    "center_y": (top + bottom) // 2,
                })

        for child in node.get("children", []):
            walk(child)

    if isinstance(tree, list):
        for n in tree:
            walk(n)
    else:
        walk(tree)

    return matches


# ─────────────────────────── WebSocket reader ──────────────────

async def reader(ws):
    try:
        while True:
            data = await ws.receive()

            # 收到断线帧，主动退出
            if data.get("type") == "websocket.disconnect":
                log.info("Phone sent disconnect frame.")
                break

            if "text" in data:
                try:
                    msg = json.loads(data["text"])
                except json.JSONDecodeError:
                    log.warning("Received non-JSON text frame, ignoring.")
                    continue

                mid = msg.get("id")
                if mid and mid in pending:
                    fut = pending[mid]
                    if not fut.done():
                        fut.set_result(msg)
                else:
                    log.debug("Unmatched text message id=%s", mid)

            elif "bytes" in data:
                raw = data["bytes"]
                if len(raw) > 36:
                    try:
                        rid = raw[:36].decode("ascii")
                    except UnicodeDecodeError:
                        log.warning("Binary frame: cannot decode id prefix, skipping.")
                        continue
                    if rid in pending:
                        fut = pending[rid]
                        if not fut.done():
                            fut.set_result({
                                "id": rid,
                                "status": "success",
                                "result": base64.b64encode(raw[36:]).decode(),
                            })
                    else:
                        log.debug("Binary frame: unmatched id=%s", rid)
                else:
                    log.warning("Binary frame too short (%d bytes), ignoring.", len(raw))

    except WebSocketDisconnect:
        log.info("Phone WebSocket disconnected.")
    except Exception as exc:
        log.error("reader() error: %s", exc)
    finally:
        await _cleanup_phone()


# ─────────────────────────── HTTP endpoints ────────────────────

@app.get("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/status")
async def status():
    return {"phone_connected": phone_ws is not None}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    global phone_ws
    await ws.accept()
    phone_ws = ws
    log.info("Phone connected: %s", ws.client)
    await reader(ws)


@app.post("/cmd")
async def http_cmd(method: str, params: str = "{}"):
    try:
        result = await send_command(method, json.loads(params))
        return result
    except RuntimeError as e:
        return {"error": str(e)}
    except TimeoutError as e:
        return {"error": str(e)}


# ─────────────────────────── MCP tools ─────────────────────────

@mcp.tool()
async def phone_analyze_screen(question: str = "描述当前屏幕上显示的内容，包括所有可见的文字、按钮和界面元素") -> str:
    """
    截图并用豆包视觉模型分析屏幕内容，返回文字描述。
    question: 你想问关于当前屏幕的具体问题。
    示例: 登录按钮在哪里？当前页面是什么？输入框有什么文字？
    """
    screenshot_b64 = await _screenshot_internal()
    if not screenshot_b64:
        return "截图失败，无法分析屏幕"
    resp = await _vision_client.chat.completions.create(
        model="ep-20260421160843-l48q6",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + screenshot_b64}},
                {"type": "text", "text": question},
            ],
        }],
    )
    return resp.choices[0].message.content


@mcp.tool()
async def phone_tap_by_description(target: str) -> str:
    """
    截图后由豆包视觉模型识别目标元素坐标并自动点击。
    target: 要点击的元素描述，例如 登录按钮、搜索框、返回箭头
    """
    screenshot_b64 = await _screenshot_internal()
    if not screenshot_b64:
        return "截图失败，无法定位元素"

    prompt = (
        "请在图片中找到\"" + target + "\"，返回其中心点坐标。"
        "只返回JSON，格式: {\"x\": 数字, \"y\": 数字, \"found\": true/false, \"reason\": \"说明\"}"
        "坐标单位是像素，原点在左上角。如果找不到，found返回false。"
    )
    resp = await _vision_client.chat.completions.create(
        model="ep-20260421160843-l48q6",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + screenshot_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    raw = resp.choices[0].message.content.strip()
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        coords = json.loads(clean)
    except json.JSONDecodeError:
        return "视觉模型返回格式无法解析: " + raw

    if not coords.get("found", False):
        return "未找到目标元素\"" + target + "\"：" + coords.get("reason", "未知原因")

    x = int(coords["x"])
    y = int(coords["y"])
    tap_resp = await send_command("tap", {"x": x, "y": y})
    return "已点击\"" + target + "\"坐标 ({}, {})，状态: {}".format(x, y, tap_resp.get("status", "unknown"))


@mcp.tool()
async def phone_tap(x: int, y: int) -> str:
    """Tap the screen at coordinates (x, y)."""
    resp = await send_command("tap", {"x": x, "y": y})
    return resp.get("status", "unknown")


@mcp.tool()
async def phone_swipe(start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 300) -> str:
    """Swipe from (start_x, start_y) to (end_x, end_y). duration in milliseconds."""
    resp = await send_command("swipe", {
        "startX": start_x,
        "startY": start_y,
        "endX": end_x,
        "endY": end_y,
        "duration": duration,
    })
    return resp.get("status", "unknown")


@mcp.tool()
async def phone_input_text(text: str, clear: bool = True) -> str:
    """
    在当前焦点输入框中输入文字。
    text: 要输入的文字
    clear: 是否先清空输入框（默认True）
    注意: 需要先点击输入框使其获得焦点。
    """
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    resp = await send_command("keyboard/input", {
        "base64_text": encoded,
        "clear": clear,
    })
    return resp.get("result", resp.get("status", "unknown"))


@mcp.tool()
async def phone_press_key(key_code: int) -> str:
    """
    按下指定键码的按键。
    常用键码: 3=HOME 4=BACK 66=ENTER 67=BACKSPACE 62=SPACE 111=ESC
    """
    resp = await send_command("keyboard/key", {"key_code": key_code})
    return resp.get("result", resp.get("status", "unknown"))


@mcp.tool()
async def phone_press_back() -> str:
    """按返回键 (BACK, keyCode=4)。"""
    resp = await send_command("keyboard/key", {"key_code": 4})
    return resp.get("result", resp.get("status", "unknown"))


@mcp.tool()
async def phone_press_home() -> str:
    """按Home键 (keyCode=3)。"""
    resp = await send_command("keyboard/key", {"key_code": 3})
    return resp.get("result", resp.get("status", "unknown"))


@mcp.tool()
async def phone_launch_app(package: str) -> str:
    """Launch an Android app by package name. Example: com.android.settings"""
    resp = await send_command("launchApp", {"package": package})
    return resp.get("result", resp.get("status", "unknown"))


@mcp.tool()
async def phone_stop_app(package: str) -> str:
    """Force-stop an Android app by package name."""
    resp = await send_command("stopApp", {"package": package})
    return resp.get("result", resp.get("status", "unknown"))


@mcp.tool()
async def phone_get_state(max_chars: int = 6000) -> str:
    """
    获取当前屏幕完整状态，包含无障碍树和手机状态（当前App、键盘是否可见等）。
    max_chars: 截断长度，避免上下文溢出（默认6000）。
    """
    resp = await send_command("state", {})
    result = resp.get("result", "")
    if isinstance(result, (dict, list)):
        text = json.dumps(result, ensure_ascii=False)
    else:
        text = str(result)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated, {} chars total]".format(len(text))
    return text


@mcp.tool()
async def phone_get_packages(filter_keyword: str = "") -> str:
    """
    获取已安装应用列表。
    filter_keyword: 过滤关键词，如 com.tencent，留空返回前100个。
    """
    resp = await send_command("packages", {})
    result = resp.get("result", [])
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            return result
    if not isinstance(result, list):
        return str(result)
    if filter_keyword:
        result = [p for p in result if filter_keyword.lower() in str(p).lower()]
    total = len(result)
    truncated = result[:100]
    out = json.dumps(truncated, ensure_ascii=False)
    if total > 100:
        out += "\n...[showing 100/{} packages, use filter_keyword to narrow]".format(total)
    return out


@mcp.tool()
async def phone_keep_awake(enabled: bool) -> str:
    """Enable or disable keep-screen-awake. enabled=True prevents screen off."""
    resp = await send_command("keepAwake", {"enabled": enabled})
    return resp.get("result", resp.get("status", "unknown"))


@mcp.tool()
async def phone_find_elements(text: str = "", class_name: str = "", clickable_only: bool = False) -> str:
    """
    从无障碍树中搜索元素，返回匹配节点列表（含中心坐标）。
    text: 按文字内容模糊匹配
    class_name: 按类名匹配，如 android.widget.Button
    clickable_only: 只返回可点击元素
    """
    resp = await send_command("state", {})
    result = resp.get("result", {})
    tree = result.get("a11y_tree", result) if isinstance(result, dict) else result

    matches = parse_nodes(tree, text_filter=text, class_filter=class_name, clickable_only=clickable_only)
    if not matches:
        return "未找到匹配元素"
    return json.dumps(matches[:20], ensure_ascii=False)


@mcp.tool()
async def phone_click_element(text: str = "", class_name: str = "", index: int = 0) -> str:
    """
    在无障碍树中找到元素并点击其中心坐标。
    text: 按文字内容匹配
    class_name: 按类名匹配
    index: 多个匹配时选第几个（从0开始）
    """
    resp = await send_command("state", {})
    result = resp.get("result", {})
    tree = result.get("a11y_tree", result) if isinstance(result, dict) else result

    matches = parse_nodes(tree, text_filter=text, class_filter=class_name)
    if not matches:
        return "未找到元素: text=\"{}\" class=\"{}\"".format(text, class_name)
    if index >= len(matches):
        return "index={} 超出范围，共找到 {} 个匹配".format(index, len(matches))

    target = matches[index]
    x = target["center_x"]
    y = target["center_y"]
    tap_resp = await send_command("tap", {"x": x, "y": y})
    return "已点击 \"{}\" 坐标({},{}) 状态:{}".format(
        target["text"], x, y, tap_resp.get("status", "unknown")
    )


@mcp.tool()
async def phone_click_element_by_index(overlay_index: int) -> str:
    """
    通过 Portal App 叠加层显示的数字编号点击对应元素。
    overlay_index: 屏幕叠加层上显示的数字
    """
    resp = await send_command("state", {})
    result = resp.get("result", {})
    tree = result.get("a11y_tree", result) if isinstance(result, dict) else result

    matches = []

    def walk(node):
        if not isinstance(node, dict):
            return
        idx = node.get("overlayIndex", node.get("index", None))
        if idx == overlay_index:
            matches.append(node)
        for child in node.get("children", []):
            walk(child)

    if isinstance(tree, list):
        for n in tree:
            walk(n)
    else:
        walk(tree)

    if not matches:
        return "未找到叠加层编号 {} 的元素".format(overlay_index)

    node = matches[0]
    bounds = node.get("boundsInScreen", {})
    x = (bounds.get("left", 0) + bounds.get("right", 0)) // 2
    y = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2
    tap_resp = await send_command("tap", {"x": x, "y": y})
    return "已点击编号{} \"{}\" 坐标({},{}) 状态:{}".format(
        overlay_index, node.get("text", ""), x, y, tap_resp.get("status", "unknown")
    )


# ─────────────────────────── MCP SSE via raw ASGI middleware ───

sse_transport = SseServerTransport("/mcp/messages/")


class MCPMiddleware:
    """Raw ASGI middleware that intercepts /mcp/* before FastAPI."""

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            method = scope.get("method", "GET")

            if path == "/mcp/sse" and method == "GET":
                try:
                    async with sse_transport.connect_sse(scope, receive, send) as (r, w):
                        await mcp._mcp_server.run(
                            r, w,
                            mcp._mcp_server.create_initialization_options(),
                        )
                except Exception as exc:
                    log.error("SSE handler error: %s", exc)
                return

            if path in ("/mcp/messages/", "/mcp/messages") and method == "POST":
                try:
                    await sse_transport.handle_post_message(scope, receive, send)
                except Exception as exc:
                    log.error("Messages handler error: %s", exc)
                return

        await self.asgi_app(scope, receive, send)


# Wrap FastAPI app — must be the last line
app = MCPMiddleware(app)
