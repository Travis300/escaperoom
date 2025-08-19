from flask import Flask, render_template

app = Flask(__name__, template_folder='app/templates', static_folder='app/static')

@app.route('/')
def home():
    return render_template('home.html')

if __name__ == '__main__':
    app.run()
