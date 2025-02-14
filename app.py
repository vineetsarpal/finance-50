import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    user_id = session.get("user_id")

    if request.method == "POST":
        cash_to_add = int(request.form.get("cash"))
        if not cash_to_add or cash_to_add < 0:
            return apology("Invalid cash amount!")
        if cash_to_add > 10000:
            return apology("max transaction limit is 10K")

        db.execute("UPDATE users SET cash = cash + ?", cash_to_add)

        # Record deposit transaction
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, type) VALUES(?, 'cash', 1, ?, 'deposit')",
                   user_id, cash_to_add)

        return redirect("/")

    else:
        """Show portfolio of stocks"""

        stocks = db.execute(
            "SELECT symbol, shares, avg_price FROM portfolio WHERE user_id = ? AND shares > 0", user_id)

        cash_row = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = float(cash_row[0]["cash"])

        return render_template("index.html", stocks=stocks, lookup=lookup, usd=usd, cash=cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        user_id = session.get("user_id")

        input_symbol = request.form.get("symbol")
        if not input_symbol:
            return apology("", 400)

        stock_data = lookup(input_symbol)
        if not stock_data:
            return apology("invalid symbol", 400)

        stock_price = stock_data["price"]
        stock_symbol = stock_data["symbol"]

        no_of_shares = request.form.get("shares")
        if not no_of_shares or no_of_shares.isalpha():
            return apology("invalid number of shares")
        if not no_of_shares.isdigit():
            return apology("fractional shares not allowed")

        no_of_shares = int(no_of_shares)

        cash_query = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = cash_query[0]["cash"]

        buy_amount = stock_price * no_of_shares

        if buy_amount > cash:
            return apology("need more cash, you broke")
        else:
            # Record transaction
            db.execute("INSERT INTO transactions (user_id, symbol, shares, price, type) VALUES(?, ?, ?, ?, 'buy')",
                       user_id, stock_symbol, no_of_shares, stock_price)

            # Update portfolio
            db.execute("""
                INSERT INTO portfolio (user_id, symbol, shares, avg_price)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(user_id, symbol) DO UPDATE SET
                       shares = shares + ?,
                       avg_price = ((shares * avg_price) + (? * ?)) / (shares + ?)
                       """,
                       user_id, stock_symbol, no_of_shares, stock_price,
                       no_of_shares,
                       no_of_shares, stock_price, no_of_shares)

            # Update user cash
            db.execute("UPDATE users SET cash = cash - ?", buy_amount)

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session.get("user_id")
    transactions = db.execute("""
        SELECT symbol, shares, price, type, timestamp
        FROM transactions
        WHERE user_id = ?
        ORDER BY timestamp DESC""",
                              user_id)
    return render_template("history.html", transactions=transactions, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

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
        stock_symbol = request.form.get("symbol")
        if not stock_symbol:
            return apology("must provide symbol", 400)

        stock_data = lookup(stock_symbol)
        if not stock_data:
            return apology("invalid symbol", 400)

        stock_name = stock_data["name"]
        stock_price = stock_data["price"]

        return render_template("quoted.html", symbol=stock_symbol, name=stock_name, price=stock_price, usd=usd)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        if not username:
            return apology("must provide a username", 400)

        password = request.form.get("password")
        if not password:
            return apology("must enter a password", 400)
        hashed_password = generate_password_hash(password)

        confirmation = request.form.get("confirmation")
        if password != confirmation:
            return apology("Passwords do not match", 400)

        db_usernames = db.execute("SELECT username FROM users WHERE username = ?", username)

        if len(db_usernames) > 0:
            return apology("username taken, pls try another username", 400)

        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hashed_password)

        user_id_row = db.execute("SELECT id from users WHERE username = ?", username)
        user_id = user_id_row[0]["id"]

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, type) VALUES(?, 'cash', 1, ?, 'deposit')",
                   user_id, 10000)

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session.get("user_id")

    if request.method == "POST":
        stock_symbol = request.form.get("symbol")
        if not stock_symbol:
            return apology("invalid stock", 403)

        no_of_shares = int(request.form.get("shares"))
        if not no_of_shares or no_of_shares < 0:
            return apology("invalid number of shares")

        current_shares_row = db.execute(
            "SELECT shares from portfolio WHERE user_id = ? AND symbol = ?", user_id, stock_symbol)
        current_shares = int(current_shares_row[0]["shares"])

        if current_shares - no_of_shares < 0:
            return apology("not enough shares")

        stock_data = lookup(stock_symbol)

        stock_price = 0
        if stock_data is not None:
            stock_price = stock_data["price"]

        sell_amount = no_of_shares * stock_price

        # Record the transaction
        db.execute("""
            INSERT INTO transactions (user_id, symbol, shares, price, type)
            VALUES (?, ?, ?, ?, 'sell')
                    """,
                   user_id, stock_symbol, -no_of_shares, stock_price)

        # Update portfolio
        db.execute("""
            UPDATE portfolio
            SET shares = shares - ?
            WHERE user_id = ? AND symbol = ? AND shares >= ?
                   """,
                   no_of_shares, user_id, stock_symbol, no_of_shares)

        if no_of_shares == current_shares:
            db.execute("DELETE FROM portfolio WHERE user_id = ? AND symbol = ?",
                       user_id, stock_symbol)

        # Update user cash
        db.execute("UPDATE users SET cash = cash + ?", sell_amount)

        return redirect("/")

    else:
        stock_symbols = db.execute(
            "SELECT DISTINCT symbol FROM portfolio WHERE user_id = ?", user_id)
        return render_template("sell.html", stocks=stock_symbols)
