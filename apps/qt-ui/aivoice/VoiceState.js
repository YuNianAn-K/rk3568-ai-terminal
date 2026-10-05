.pragma library

// Transport state is authoritative; visual states never control the service.
function visualState(state, connected) {
    if (!connected || state === "offline") return "offline";
    switch (state) {
    case "error": return "error";
    case "starting":
    case "recording": return "listening";
    case "recognizing":
    case "thinking":
    case "replying": return "thinking";
    case "playing": return "speaking";
    default: return "idle";
    }
}

function action(state, connected) {
    if (!connected || state === "offline") return "reconnect";
    if (state === "idle" || state === "error") return "start";
    if (state === "recording") return "stop";
    return "none";
}

function title(state, connected, message) {
    if (!connected || state === "offline") return "语音服务未连接";
    if (state === "idle" && String(message).indexOf("待唤醒") === 0) return "待唤醒 · 小爱同学";
    switch (state) {
    case "initializing": return "正在准备";
    case "starting": return "准备聆听";
    case "recording": return "我在听";
    case "recognizing": return "正在整理声音";
    case "thinking": return "正在思考";
    case "replying": return "正在准备回答";
    case "playing": return "正在与你分享";
    case "error": return "这次没有完成";
    default: return "随时与你对话";
    }
}

function hint(state, connected, message) {
    if (!connected || state === "offline") return "离线 · 轻触麦克风重新连接";
    if (state === "idle" && String(message).indexOf("待唤醒") === 0) return "说小爱同学，提示音后说话 · 按键仍可用";
    if (state === "recording" && String(message).indexOf("自动结束") >= 0) return "说完自动结束，最多 10 秒 · 也可轻触结束";
    switch (state) {
    case "initializing": return "语音服务正在启动，请稍候";
    case "starting": return "正在打开麦克风，请稍候";
    case "recording": return "自然说话，说完后再次轻触";
    case "recognizing": return "请稍候，正在识别你的话";
    case "thinking": return "正在生成回答";
    case "replying": return "文字已到来，语音正在准备";
    case "playing": return "播放结束后可以开始下一轮";
    case "error": return "轻触麦克风重新尝试";
    default: return "轻触光球或麦克风，开始对话";
    }
}

function errorKey(roundId, message) {
    return String(roundId) + ":" + String(message);
}
