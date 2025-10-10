from flask import Flask, request, jsonify
from flask_cors import CORS
from g4f.client import Client
import random, time

app = Flask(__name__)
CORS(app)

client = Client()

# 🎯 Системная инструкция — чтобы GPT отвечал как надо
SYSTEM_PROMPT = """Ты — умный искусственный интеллект на архитектуре GPT-5.
Отвечай лаконично, без "объяснений", если пользователь просит код — давай только код,
чисто в ```<язык>``` блоках без описаний.
Если просят текст — отвечай естественно, как человек.
Не добавляй лишний текст вроде "вот пример" или "объяснение".
"""

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"reply": "❗Введите сообщение."})

        # 🚀 Попробуем несколько провайдеров по очереди
        providers = ["Acytoo", "GptGo", "Phind", "Bing", "DeepAi"]
        for provider_name in providers:
            try:
                print(f"[INFO] Попытка: {provider_name}")
                response = client.chat.completions.create(
                    model="gpt-4o",
                    provider=provider_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                )
                reply = response.choices[0].message.content.strip()
                print(f"[SUCCESS] Ответ от {provider_name}")
                return jsonify({"reply": reply})
            except Exception as e:
                print(f"[FAIL] {provider_name}: {e}")
                time.sleep(random.uniform(0.5, 1.5))
                continue

        return jsonify({"error": "❌ Все провайдеры недоступны. Попробуй позже."}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/')
def home():
    return "✅ GPT-5 сервер запущен и отвечает без объяснений!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
