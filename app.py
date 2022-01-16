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
seek_offset = 0


class Audiobook(db.Document):
    title = db.StringField()
    location = db.StringField()
    files = db.ListField(db.StringField())
    is_hidden = db.BooleanField(default=False)
    thumbnail_fn = db.StringField()
    play_file_index = db.IntField(default=0)
    added_epochtime = db.IntField(default=0)
    last_played_epochtime = db.IntField(default=0)
    playing_since_epochtime = db.IntField(default=0)
    seconds_seek = db.IntField(default=0)
    notes = db.StringField()
    meta = {"indexes": ["last_played_epochtime"]}

    def get_book_files(self):
        files = list(Path(self.location).glob("*.mp3"))
        files += list(Path(self.location).glob("*.m4b"))
        return files


@app.route("/", methods=["GET", "POST"])
def index():
    if flask.request.method == "POST":
        location = flask.request.form.get("location")
        if Path(location).is_dir():
            a = Audiobook(location=location, added_epochtime=int(time.time()))
            a.save()
        return flask.redirect(flask.url_for("index"))
    if flask.request.method == "GET":
        books = Audiobook.objects.order_by("-last_played_epochtime")
        return flask.render_template(
            "index.jinja2",
            books=books,
            active_book=active_book,
            show_all=flask.request.args.get("show_all"),
        )


def set_thumbnail(book):
    if book.thumbnail_fn and (Path("static") / book.thumbnail_fn).exists():
        return
    images = list(Path(book.location).glob("*.jpg"))
    images += list(Path(book.location).glob("*.png"))
    if images:
        Path("static").mkdir(exist_ok=True)
        dest = Path("static") / images[0].name
        if not dest.exists():
            dest.symlink_to(images[0].absolute())
        book.thumbnail_fn = images[0].name
        book.save()


@app.route("/book/<book_id>/toggle")
def toggle_book_vis(book_id):
    book = Audiobook.objects.filter(id=book_id).first_or_404()
    if book != active_book:
        book.is_hidden = not book.is_hidden
        book.save()
    return flask.redirect(flask.url_for("index"))


def sorted_book_files(files):
    def book_key(fn):
        num = str()
        for c in fn.name:
            if c.isdigit():
                num += str(c)
            elif num:
                # return the first number found that's less than 3 digits
                # more than 3 digits probably a year
                if len(num) <= 3:
                    return int(num)
                else:
                    num = str()
        return int("0" + num)

    return sorted(files, key=book_key)


@app.route("/book/<book_id>", methods=["GET", "POST"])
def book(book_id):
    book = Audiobook.objects.filter(id=book_id).first_or_404()
    if flask.request.method == "POST":
        notes = flask.request.form.get("notes")
        book.notes = notes
        book.save()
        return flask.redirect(flask.url_for("book", book_id=book.id))
    book_location = Path(book.location).absolute()
    book.location = str(book_location)
    book.title = book_location.name
    book.save()
    set_thumbnail(book)
    files = sorted_book_files(book.get_book_files())
    book.files = list(map(str, files))
    last_played = humanize.naturaldelta(int(time.time()) - book.last_played_epochtime)

    return flask.render_template(
        "book.jinja2",
        book=book,
        active_book=active_book,
        bg_image=book.thumbnail_fn,
        last_played=last_played,
        seek_offset=seek_offset,
    )


@app.route("/seek/<amt>")
def seek(amt):
    if not active_book:
        flask.abort(404)
    player.seek(int(amt))
    global seek_offset
    seek_offset += int(amt)
    return flask.redirect(flask.url_for("book", book_id=active_book.id))


@app.route("/play/<book_id>/<file_index>")
def play_file(book_id, file_index):
    threading.Thread(target=play_thread, args=(book_id, int(file_index))).start()
    return flask.redirect(flask.url_for("book", book_id=book_id))


def play_thread(book_id, file_index=None):
    stop()
    print(book_id, file_index)
    global active_book
    global seek_offset
    active_book = Audiobook.objects.filter(id=book_id).first_or_404()
    files = sorted_book_files(active_book.get_book_files())
    active_book.files = list(map(str, files))
    if file_index is not None:
        active_book.play_file_index = file_index
        active_book.seconds_seek = 0
    active_book.save()
    while True:
        active_book.last_played_epochtime = int(time.time())
        active_book.save()
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
    return flask.redirect(flask.url_for("book", book_id=book_id))


@app.route("/toggle_play")
def toggle_play():
    if active_book:
        stop()
    else:
        last_book = Audiobook.objects.order_by("-last_played_epochtime").first_or_404()
        play(last_book.id)
    return "OK"


@app.route("/stop")
def stop():
    global active_book
    global seek_offset
    if not active_book:
        return
    time_now2 = time.time()
    time_now1 = active_book.playing_since_epochtime
    advance_time = time_now2 - time_now1
    print(time_now1, time_now2, advance_time)
    active_book.seconds_seek += max(0, math.floor(advance_time - 3)) + seek_offset
    seek_offset = 0
    active_book.save()
    book_id = active_book.id
    active_book = None
    player.stop()
    return flask.redirect(flask.url_for("book", book_id=book_id))


def main():
    app.run(port=6859, debug=True)


if __name__ == "__main__":
    argh.dispatch_command(main)
