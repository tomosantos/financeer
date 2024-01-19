import os

# For our rotes
from cs50 import SQL
from flask import flash, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

# For building our graphs
import pandas as pd
import json
import plotly
import plotly.express as px
from pandas_datareader import data as pdr
import yfinance as yf
from datetime import datetime

# Importing some helping functions
from application.helpers import login_required, lookup, usd

# Import app from __init__.py
from application import app

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]

    transactions = db.execute("SELECT symbol, SUM(shares) AS shares, price, SUM(price) as total FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0", user_id)

    cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = cash[0]["cash"]

    total = cash

    for i in range(len(transactions)):
        transactions[i]["total"] = transactions[i]["shares"] * transactions[i]["price"]

        total += transactions[i]["total"]

        transactions[i]["total"] = usd(transactions[i]["total"])
        transactions[i]["price"] = usd(transactions[i]["price"])

    name = db.execute("SELECT name FROM users WHERE id = ?", user_id)
    name = name[0]["name"]

    return render_template("index.html", stocks=transactions, cash=usd(cash), total=usd(total), name=name)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            message = "Missing symbol!"
            return render_template("buy.html", message=message)

        symbol = lookup(symbol.upper())

        if symbol is None:
            message = "Invalid symbol!"
            return render_template("buy.html", message=message)

        stock = symbol["symbol"]
        price = symbol["price"]

        shares = request.form.get("shares")
        if not shares:
            message = "Missing shares!"
            return render_template("buy.html", message=message)
        elif shares.isdigit() == False:
            message = "Invalid shares!"
            return render_template("buy.html", message=message)
        elif float(shares).is_integer() == False:
            message = "Invalid shares!"
            return render_template("buy.html", message=message)
        elif int(shares) < 0:
            message = "Invalid shares!"
            return render_template("buy.html", message=message)

        total = price * int(shares)

        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = cash[0]["cash"]

        if total > cash:
            message = "Can't afford!"
            return render_template("buy.html", message=message)

        new_cash = cash - total

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)", user_id, stock, shares, price)
        db.execute("UPDATE users SET (cash) = ? WHERE id = ?", new_cash, user_id)

        flash("Bought!")

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    transactions = db.execute("SELECT symbol, shares, price, date FROM transactions WHERE user_id = ?", user_id)

    for i in range(len(transactions)):
        transactions[i]["price"] = usd(transactions[i]["price"])

    return render_template("history.html", transactions=transactions)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            message = "Must provide username!"
            return render_template("login.html", message=message)

        # Ensure password was submitted
        elif not request.form.get("password"):
            message = "Must provide password!"
            return render_template("login.html", message=message)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            message = "Invalid username and/or password!"
            return render_template("login.html", message=message)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            message = "Missing symbol!"
            return render_template("quote.html", message=message)

        symbol = lookup(symbol.upper())
        if not symbol:
            message = "Invalid symbol!"
            return render_template("quote.html", message=message)

        share = symbol["symbol"]
        price = usd(symbol["price"])

        return render_template("quoted.html", share=share, price=price)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation_password = request.form.get("confirmation")

        if not name or not username or not password or not confirmation_password:
            message = "Please enter a valid name and/or username and/or password!"
            return render_template("register.html", message=message)

        if len(username) < 4 or not username.isalnum():
            message = "Username should be a minimum of four alphanumeric (A-z, 0-9) characters!"
            return render_template("register.html", message=message)

        if confirmation_password != password:
            message = "The passwords don't match!"
            return render_template("register.html", message=message)

        password_hash = generate_password_hash(password)

        try:
            new_user = db.execute("INSERT INTO users (username, hash, name) VALUES (?, ?, ?)", username, password_hash, name)
        except:
            message = "The username already exists."
            return render_template("register.html", message=message)

        session["user_id"] = new_user

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        user_id = session["user_id"]

        symbol = request.form.get("symbol")
        if not symbol:
            message = "Missing symbol!"
            return render_template("sell.html", message=message)

        symbol = lookup(symbol)
        stock = symbol["symbol"]
        price = symbol["price"]

        shares = int(request.form.get("shares"))
        if not shares:
            message = "Missing shares!"
            return render_template("sell.html", message=message)
        if shares < 0:
            message = "Invalid shares!"
            return render_template("sell.html", message=message)

        transaction_value = price * shares

        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = cash[0]["cash"]

        user_shares = db.execute("SELECT symbol, SUM(shares) AS shares FROM transactions WHERE user_id = ? AND symbol = ? GROUP BY symbol", user_id, stock)
        user_shares = user_shares[0]["shares"]

        if shares > user_shares:
            message = "Too many shares!"
            return render_template("sell.html", message=message)

        new_cash = cash + transaction_value

        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, user_id)
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)", user_id, stock, (-1) * shares, price)

        flash("Sold!")

        return redirect("/")
    else:
        user_id = session["user_id"]
        stocks = db.execute("SELECT symbol FROM transactions WHERE user_id = ? GROUP BY symbol ORDER BY symbol", user_id)

        return render_template("sell.html", stocks=stocks)

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "POST":
        deposit = request.form.get("deposit")
        if not deposit:
            message = "Missing deposit!"
            return render_template("deposit.html", message=message)

        elif int(deposit) < 0:
            message = "Invalid deposit!"
            return render_template("deposit.html", message=message)

        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = cash[0]["cash"]

        new_cash = cash + int(deposit)

        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, user_id)

        flash("Deposited!")

        return redirect("/")

    else:
        return render_template("deposit.html")

@app.route("/dash")
@login_required
def dash():
    # graph
    user_id = session["user_id"]
    shares = db.execute("SELECT symbol, shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0", user_id)

    graphsJSON = []

    start_date = datetime(2020, 1, 1)
    end_date = datetime.now()

    yf.pdr_override()

    for i in range(len(shares)):
        symbol = shares[i]["symbol"]

        df = pdr.get_data_yahoo(symbol, start_date, end_date)

        fig = px.line(df, x=df.index, y="Close", title=f"Stock Fluctuation for {symbol}")
        fig['data'][0]['line']['color']='rgb(245, 14, 59)'
        fig['data'][0]['line']['width']= 4
        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        if graphJSON:
            graphsJSON.append(graphJSON)

    counter = 0
    indexes = []

    for i in range(len(graphsJSON)):
        counter += 1
        indexes.append(counter)

    # gathering stock information from transactions table
    transactions = db.execute("SELECT symbol, SUM(shares) AS shares, price, SUM(price) as total FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0", user_id)

    for i in range(len(transactions)):
        transactions[i]["total"] = transactions[i]["shares"] * transactions[i]["price"]
        transactions[i]["total"] = usd(transactions[i]["total"])
        transactions[i]["price"] = usd(transactions[i]["price"])

    return render_template("dash.html", graphsJSON=graphsJSON, indexes=indexes, stocks=transactions)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user_id = session["user_id"]
    currentname = db.execute("SELECT name FROM users WHERE id = ?", user_id)
    currentusername = db.execute("SELECT username FROM users WHERE id = ?", user_id)
    current_hash_password = db.execute("SELECT hash FROM users WHERE id = ?", user_id)

    currentname = currentname[0]["name"]
    currentusername = currentusername[0]["username"]
    current_hash_password = current_hash_password[0]["hash"]

    if request.method == "POST":
        # edit name
        name = request.form.get("change_name").strip()

        if name:
            db.execute("UPDATE users SET name = ? WHERE id = ?", name, user_id)

            currentname = name
            message1 = "Name has sucessfully changed!"

            return render_template("settings.html", message1=message1, currentname=currentname, currentusername=currentusername)

        # change username
        username = request.form.get("change_username").strip()

        if username:
            if len(username) < 4 or not username.isalnum():
                message2 = "Username should be a minimum of four alphanumeric (A-z, 0-9) characters!"
                return render_template("settings.html", message2=message2, currentname=currentname, currentusername=currentusername)

            try:
                db.execute("UPDATE users SET username = ? WHERE id = ?", username, user_id)
                currentusername = username
            except:
                message2 = "Username has been taken. Please pick a different username!"
                return render_template("settings.html", message2=message2, currentname=currentname, currentusername=currentusername)

            message2 = "Username has successfully changed!"
            return render_template("settings.html", message2=message2, currentname=currentname, currentusername=currentusername)

        # change password
        currentpassword = request.form.get("currentpassword").strip()
        newpassword = request.form.get("newpassword").strip()

        # newpassword is hashed, so it can be used to check_password_hash
        password = generate_password_hash(newpassword)
        confirmpassword = request.form.get("confirmpassword").strip()

        if currentpassword and newpassword and confirmpassword:
            if len(newpassword) < 8:
                message3 = "Password should be a minimum of eight characters!"
                return render_template("settings.html", message3=message3, currentname=currentname, currentusername=currentusername)

            if not check_password_hash(current_hash_password, currentpassword):
                message3 = "Current password is incorrect!"
                return render_template("settings.html", message3=message3, currentname=currentname, currentusername=currentusername)

            if not check_password_hash(password, confirmpassword):
                message3 = "New password and confirmation don't match!"
                return render_template("settings.html", message3=message3, currentname=currentname, currentusername=currentusername)

            db.execute("UPDATE users SET hash = ? WHERE id = ?", password, user_id)
            message3 = "Password has successfully changed!"
            return render_template("settings.html", message3=message3, currentname=currentname, currentusername=currentusername)

        return redirect("/")

    else:
        message1 = " "
        return render_template("settings.html", currentname=currentname, currentusername=currentusername, message1=message1)
