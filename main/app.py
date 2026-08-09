import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, render_template

from capital.widget import market_summary_bp
from dart.widget import dart_bp
from news.widget import news_summary_bp
from policy.widget import policy_bp

app = Flask(__name__)
app.register_blueprint(news_summary_bp)
app.register_blueprint(market_summary_bp)
app.register_blueprint(policy_bp)
app.register_blueprint(dart_bp)


@app.route("/")
def home():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
