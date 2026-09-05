import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, render_template

from capital.widget import capital_bp
from issuance.widget import issuance_bp
from policy.widget import policy_bp
from research.widget import research_bp

app = Flask(__name__)
# PoC: 정적 파일(css/js)도 캐시하지 않아 기기 간 최신본이 바로 반영되게 한다.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.register_blueprint(capital_bp)
app.register_blueprint(policy_bp)
app.register_blueprint(research_bp)
app.register_blueprint(issuance_bp)


@app.route("/")
def home():
    return render_template("index.html")


@app.after_request
def _no_store(resp):
    # HTML·CSS·JS 모두 캐시하지 않아 기기 간(특히 모바일) 최신본이 바로 반영되게 한다.
    if resp.mimetype in ("text/html", "text/css", "application/javascript", "text/javascript"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    app.run(debug=True, port=5000)
