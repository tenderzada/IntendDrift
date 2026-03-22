"""A minimal Flask app with a bug: /profile crashes when user_bio is None."""

from flask import Flask, render_template

app = Flask(__name__)

# Simulated user database
USERS = {
    "alice": {"name": "Alice Chen", "email": "alice@example.com", "bio": "Software engineer who loves hiking."},
    "bob": {"name": "Bob Smith", "email": "bob@example.com", "bio": None},  # <-- bio is None, causes crash
    "carol": {"name": "Carol Davis", "email": "carol@example.com", "bio": "Data scientist and cat lover."},
    "dave": {"name": "Dave Wilson", "email": "dave@example.com", "bio": None},  # <-- also None
}


@app.route("/")
def index():
    return render_template("index.html", users=USERS)


@app.route("/profile/<username>")
def profile(username):
    user = USERS.get(username)
    if user is None:
        return "User not found", 404
    # BUG: This will crash with UndefinedError when bio is None
    # because the template tries to call .upper() on bio
    return render_template("profile.html", user=user, username=username)


@app.route("/about")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(debug=True)
