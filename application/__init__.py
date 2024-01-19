from flask import Flask
from flask_session import Session

from application.helpers import usd

# Configure application
app = Flask(__name__)

# Custom Filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

from application import routes
