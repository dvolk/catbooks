# catbooks - web audiobook player

<table>
<tr>
<th>Audiobook index</th>
<th>Audiobook details<th>
</tr>
<tr>
<td><img src="https://i.imgur.com/Tnt4x6m.png"></img></td>
<td><img src="https://i.imgur.com/y7L86Ud.png"></img></td>
</tr>
</table>

# Features

- Play audiobooks using mpv for best performance.
- Remembers which chapter and time you were on for each audiobook.
- Add notes for audiobooks.
- Finds thumbnails for audiobooks.

## Installation

You will need mongodb:

    apt install mongodb-server

No further database configuration is needed.

    git clone https://github.com/dvolk/catbooks
    cd catbooks
    virtualenv env
    source env/bin/activate
    pip3 install -r requirements.txt

Install `mpv` if you don't have it:

    apt install mpv

## Running

    python3 app.py

## Adding books

Put the audiobook directory in the `catbooks` directory and open the web page and add the directory name in the form on the bottom of the page.
