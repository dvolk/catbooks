import math
import threading
import time
from pathlib import Path

import argh
import flask
import flask_mongoengine
import humanize
import mpv

app = flask.Flask(__name__)
app.secret_key = "secret"
app.config["MONGODB_DB"] = "catbooks-1"
db = flask_mongoengine.MongoEngine(app)
player = mpv.MPV()
active_book = None


class Audiobook(db.Document):
    title = db.StringField()
    location = db.StringField()
    files = db.ListField(db.StringField())
    play_file_index = db.IntField(default=0)
    added_epochtime = db.IntField(default=0)
    playing_since_epochtime = db.IntField(default=0)
    seconds_seek = db.IntField(default=0)


@app.route("/")
def index():
    books = Audiobook.objects
    return flask.render_template(
        "index.jinja2", books=books, active_book=active_book, humanize=humanize
    )


@app.route("/book/<book_id>")
def book(book_id):
    book = Audiobook.objects.filter(id=book_id).first_or_404()
    if not book.files:
        files = list(Path(book.location).glob("*.mp3"))
        files += list(Path(book.location).glob("*.m4b"))
        files = sorted(files, key=lambda x: x.name)
        book.files = list(map(str, files))

    return flask.render_template("book.jinja2", book=book)


@app.route("/play/<book_id>/<file_index>")
def play_file(book_id, file_index):
    stop()
    threading.Thread(target=play_thread, args=(book_id, int(file_index))).start()
    return flask.redirect(flask.url_for("book", book_id=book_id))


def play_thread(book_id, file_index=None):
    print(book_id, file_index)
    global active_book
    active_book = Audiobook.objects.filter(id=book_id).first_or_404()
    files = list(Path(active_book.location).glob("*.mp3"))
    files += list(Path(active_book.location).glob("*.m4b"))
    files = sorted(files, key=lambda x: x.name)
    if not active_book.files:
        active_book.files = list(map(str, files))
    if file_index:
        active_book.play_file_index = file_index
        active_book.seconds_seek = 0
    active_book.save()
    while True:
        fn = list(files)[active_book.play_file_index]
        print(f"Playing {fn} {active_book.seconds_seek}")
        player.play(str(fn))
        time_now1 = time.time()
        active_book.playing_since_epochtime = time_now1
        active_book.save()
        player.wait_until_playing()
        player.seek(active_book.seconds_seek)
        player.wait_for_event("end-file")
        print(f"file {fn} ended")
        if not active_book:
            break
        if active_book.play_file_index >= len(files):
            break
        else:
            active_book.play_file_index += 1
            active_book.seconds_seek = 0
            active_book.save()


@app.route("/play/<book_id>")
def play(book_id):
    threading.Thread(target=play_thread, args=(book_id, None)).start()
    return flask.redirect(flask.url_for("index"))


@app.route("/stop")
def stop():
    global active_book
    if not active_book:
        return
    time_now2 = time.time()
    time_now1 = active_book.playing_since_epochtime
    advance_time = time_now2 - time_now1
    print(time_now1, time_now2, advance_time)
    active_book.seconds_seek += max(0, math.floor(advance_time - 3))
    active_book.save()
    active_book = None
    player.stop()
    return flask.redirect(flask.url_for("index"))


def main():
    app.run(port=6859, debug=True)


if __name__ == "__main__":
    argh.dispatch_command(main)