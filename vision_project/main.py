from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello, World! The server is working."

# Make sure the if __name__ == '__main__': block is GONE
