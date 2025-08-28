from flask import Flask, request, jsonify, render_template
from database import init_db, get_conn
from chatbot_engine import run_message, branch_thread

app = Flask(__name__)
init_db()

# ------------------ UI ROUTES ------------------

@app.route("/")
def index():
    """List all threads"""
    threads = get_conn().execute(
        "SELECT * FROM threads ORDER BY created_at DESC"
    ).fetchall()
    return render_template("index.html", threads=threads)

@app.route("/chat-ui/<int:thread_id>")
def chat_ui(thread_id):
    """Chat UI for one thread"""
    messages = get_conn().execute(
        "SELECT * FROM messages WHERE thread_id=? ORDER BY created_at",
        (thread_id,)
    ).fetchall()
    return render_template("chat.html", thread_id=thread_id, messages=messages)


# ------------------ API ROUTES ------------------

# --- Users ---
@app.route("/users", methods=["POST"])
def create_user():
    username = request.json["username"]
    try:
        conn = get_conn()
        conn.execute("INSERT INTO users (username) VALUES (?)", (username,))
        conn.commit()
        return jsonify({"message": "User created"}), 201
    except:
        return jsonify({"error": "User exists"}), 400

# --- Threads ---
@app.route("/threads", methods=["POST"])
def create_thread():
    data = request.json
    user_id = data["user_id"]
    title = data.get("title", "New Chat")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO threads (user_id, title) VALUES (?, ?)", (user_id, title))
    conn.commit()
    return jsonify({"thread_id": cur.lastrowid, "title": title})

@app.route("/threads/<int:user_id>", methods=["GET"])
def get_user_threads(user_id):
    rows = get_conn().execute(
        "SELECT * FROM threads WHERE user_id=?", (user_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

# --- Chat ---
@app.route("/chat/<int:thread_id>", methods=["POST"])
def chat(thread_id):
    msg = request.json["message"]

    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (thread_id, role, content) VALUES (?, 'user', ?)",
        (thread_id, msg),
    )
    conn.commit()

    bot_reply = run_message(str(thread_id), msg)

    conn.execute(
        "INSERT INTO messages (thread_id, role, content) VALUES (?, 'assistant', ?)",
        (thread_id, bot_reply),
    )
    conn.commit()
    conn.close()

    return jsonify({"user": msg, "assistant": bot_reply})

@app.route("/chat/<int:thread_id>", methods=["GET"])
def get_chat(thread_id):
    rows = get_conn().execute(
        "SELECT * FROM messages WHERE thread_id=? ORDER BY created_at",
        (thread_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])

# --- Edit ---
@app.route("/edit/<int:msg_id>", methods=["PUT"])
def edit_message(msg_id):
    new_text = request.json["content"]
    conn = get_conn()
    conn.execute("UPDATE messages SET content=? WHERE id=?", (new_text, msg_id))
    conn.commit()
    return jsonify({"message": "Edited"})

# --- Branch thread ---
@app.route("/branch", methods=["POST"])
def branch():
    data = request.json
    old_thread = str(data["old_thread"])
    new_thread = str(data["new_thread"])
    replace_msg = data.get("replace_msg")

    # create new thread in DB
    conn = get_conn()
    conn.execute("INSERT INTO threads (user_id, title) VALUES (?, ?)",
                 (data.get("user_id", 1), f"Branch of {old_thread}"))
    conn.commit()

    bot_reply = branch_thread(old_thread, new_thread, replace_msg)
    return jsonify({
        "message": f"Branched {old_thread} -> {new_thread}",
        "reply": bot_reply
    })


# ------------------ RUN ------------------

if __name__ == "__main__":
    app.run(debug=True)
