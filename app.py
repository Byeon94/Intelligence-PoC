from flask import Flask, render_template

from widgets.news_summary import news_summary_bp

app = Flask(__name__)
app.register_blueprint(news_summary_bp)


@app.route("/")
def home():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
