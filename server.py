from flask import Flask, request, jsonify
from g4f.client import Client
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # чтобы сайт мог обращаться к серверу

client = Client()

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message")

    response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": user_message}],
)

    answer = response.choices[0].message.content
    return jsonify({"reply": answer})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

