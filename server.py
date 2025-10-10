from flask import Flask, request, jsonify
from flask_cors import CORS
from g4f.client import Client
from g4f.Provider import Yqcloud  # стабильный бесплатный провайдер

app = Flask(__name__)
CORS(app)

client = Client()

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "")

        response = client.chat.completions.create(
            model="gpt-4o",
            provider=Yqcloud,  # бесплатный, не требует логина
            messages=[
                {"role": "system", "content": "Ты — ChatGPT на архитектуре GPT-5. Отвечай умно, подробно и естественно."},
                {"role": "user", "content": user_message}
            ],
        )

        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/')
def home():
    return "✅ GPT-5 AI сервер работает!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
