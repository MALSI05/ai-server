# server.py
import os
import time
import traceback
import importlib
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from g4f.client import Client

app = Flask(__name__, static_folder="public", static_url_path="/")
CORS(app)

client = Client()

# Список имен провайдеров, которые мы попытаемся импортировать (в таком порядке)
_PROVIDER_CANDIDATES = [
    "Yqcloud", "Acytoo", "FreeGpt", "GptFree", "Bing", "AcyToo", "AcytooProvider"
]

# Список моделей (порядок попыток)
_MODELS = ["gpt-4o", "gpt-4", "gpt-3.5-turbo"]


def load_providers():
    """Динамически импортирует доступные провайдеры из g4f.Provider."""
    providers = []
    try:
        prov_mod = importlib.import_module("g4f.Provider")
    except Exception:
        # Если модуля нет — вернём пустой список
        return providers

    for name in _PROVIDER_CANDIDATES:
        try:
            cls = getattr(prov_mod, name)
            providers.append((name, cls))
        except Exception:
            # пробуем импортировать как подпакет g4f.Provider.<name> (на случай разной структуры)
            try:
                sub = importlib.import_module(f"g4f.Provider.{name}")
                cls = getattr(sub, name)
                providers.append((name, cls))
            except Exception:
                continue
    return providers


def extract_reply_from_response(resp):
    """
    Универсальный парсер ответа от g4f.
    Поддерживает:
      - строки
      - объекты с .choices[0].message.content
      - генераторы/итераторы (стримы) — соберём текстовые части
      - словари с ключами text/content/reply/answer
    """
    try:
        if resp is None:
            return ""

        # Если это уже строка
        if isinstance(resp, str):
            return resp.strip()

        # Если у объекта есть choices (как у стандартного OpenAI-подобного ответа)
        try:
            choices = getattr(resp, "choices", None)
            if choices:
                # первая попытка: .choices[0].message.content
                try:
                    first = choices[0]
                    # может быть объект с .message.content
                    msg = getattr(getattr(first, "message", None), "content", None)
                    if msg:
                        return str(msg).strip()
                    # или .text
                    txt = getattr(first, "text", None)
                    if txt:
                        return str(txt).strip()
                    # если first — dict
                    if isinstance(first, dict):
                        for k in ("message", "content", "text"):
                            if k in first and isinstance(first[k], str):
                                return first[k].strip()
                except Exception:
                    pass
        except Exception:
            pass

        # Если пришёл dict-like
        if isinstance(resp, dict):
            for k in ("reply", "answer", "text", "content"):
                v = resp.get(k)
                if isinstance(v, str):
                    return v.strip()
            # иногда вложенно
            for k in resp:
                v = resp.get(k)
                if isinstance(v, str) and len(v) > 0:
                    return v.strip()

        # Если это итератор / генератор (可能 стрим)
        if hasattr(resp, "__iter__") and not isinstance(resp, (dict, list, tuple, bytes)):
            out = ""
            try:
                for chunk in resp:
                    # chunk может быть строкой, dict или объект
                    if chunk is None:
                        continue
                    if isinstance(chunk, str):
                        out += chunk
                    elif isinstance(chunk, dict):
                        # ищем привычные поля
                        for k in ("text", "content", "reply"):
                            if k in chunk and isinstance(chunk[k], str):
                                out += chunk[k]
                        # иногда chunk содержит 'choices'
                        if "choices" in chunk and isinstance(chunk["choices"], list):
                            for c in chunk["choices"]:
                                if isinstance(c, dict):
                                    if "delta" in c and isinstance(c["delta"], str):
                                        out += c["delta"]
                                    elif "text" in c and isinstance(c["text"], str):
                                        out += c["text"]
                    else:
                        # попытка взять строковое представление
                        try:
                            s = str(chunk)
                            out += s
                        except Exception:
                            continue
                if out:
                    return out.strip()
            except TypeError:
                # неитерируемый объект
                pass

        # На крайний случай — строковое представление объекта
        return str(resp).strip()
    except Exception:
        # в случае нештатного поведения — вернём traceback как текст (для логов)
        return f"(parse error) {traceback.format_exc()}"


@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_message = data.get("message", "")
        if not user_message:
            return jsonify({"error": "Empty message"}), 400

        system_prompt = (
            "Ты — ChatGPT в стиле GPT-5. Отвечай ясно, подробно, вежливо. "
        )

        providers = load_providers()  # [(name, cls), ...]

        last_exc = None

        # Сначала попробуем без провайдера (иногда это работает)
        models_tried = []
        attempt_order = [None] + providers  # None означает без указания provider

        for prov in attempt_order:
            prov_name = "default" if prov is None else prov[0]
            prov_cls = None if prov is None else prov[1]
            for model in _MODELS:
                models_tried.append((prov_name, model))
                try:
                    print(f"[g4f] Попытка: provider={prov_name}, model={model}")
                    kwargs = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                    }
                    if prov_cls is not None:
                        kwargs["provider"] = prov_cls

                    response = client.chat.completions.create(**kwargs)

                    reply = extract_reply_from_response(response)
                    if reply:
                        print(f"[g4f] Успех: provider={prov_name}, model={model}")
                        return jsonify({"reply": reply}), 200

                    # если пусто — запомним исключение и пробуем дальше
                except Exception as e:
                    last_exc = e
                    print(f"[g4f] Ошибка при provider={prov_name}, model={model}: {e}")
                    traceback.print_exc()
                    # небольшая пауза между попытками
                    time.sleep(0.3)
                    continue

        # Если все попытки провалились — вернём понятный ответ с логом
        msg = "Все провайдеры/модели недоступны. Попытки: " + ", ".join(
            [f"{p}/{m}" for p, m in models_tried]
        )
        if last_exc:
            msg += f" | Последняя ошибка: {type(last_exc).__name__}: {str(last_exc)}"
        print("[g4f] FATAL: " + msg)
        return jsonify({"error": msg}), 502

    except Exception as e:
        print("Ошибка в /api/chat: ", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def index():
    # Если у тебя есть публичная папка с index.html (frontend), она будет отдана:
    index_path = os.path.join(app.static_folder or ".", "index.html")
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, "index.html")
    return "✅ GPT server is running. Use POST /api/chat", 200


if __name__ == "__main__":
    # PORT для Render → Render ожидает, что приложение будет слушать PORT (Env var)
    port = int(os.environ.get("PORT", 10000))
    # В режиме разработки можно оставить app.run, но в проде лучше gunicorn
    print(f"Starting app on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
