> [!WARNING]
> I can't guarantee PaperDaemon will never damage one of your notebooks. PaperDaemon checks each page in the cloud
> before writing it, and never writes over newer work from the tablet. PaperDaemon keeps copies of the pages it changes
> on your PC. It was tested thoroughly on a reMarkable Paper Pro running software 3.29.1.0 - tablet software updates
> may break PaperDaemon, proceed at your own risk. If you find any issues with PaperDaemon, or functionality that you
> believe could be better, I encourage you to fork your own branch and make any changes you think are worth while.

# PaperDaemon

An assistant for the reMarkable tablet that runs on your Windows PC, with the AI models you choose. Write a request
on a page, tag the page, and PaperDaemon does the work on that page. Every page shown here was made by PaperDaemon
running Qwen 3.8 27B, with pictures by FLUX.2 Klein.

**[Download for Windows](../../releases/latest)** (`PaperDaemon_<version>_x64-setup.exe`, under Assets)

![The page editor, with a decomposed painting selected](docs/images/editor.png)

## Decompose

Any picture, redrawn as pen strokes and sent to a notebook page. On the tablet every stroke is ink: erase it, draw
over it, select it and move it.

![The Decompose screen](docs/images/decompose-screen.png)

## Mirror

![The library](docs/images/library.png)

![The pen menu](docs/images/editor-pens.png)

## Daemon

![The Daemon screen, with a notebook's notes](docs/images/daemon.png)

## Lineup

![The Lineup: the text model on this PC, its harness and its start script](docs/images/lineup.png)

![The Lineup: the image model and its start script](docs/images/lineup-image.png)

![The Lineup: web search on this PC and its start script](docs/images/lineup-network.png)

## Settings

![Settings](docs/images/settings.png)

## On the page

Each request was typed on a test notebook and worked by PaperDaemon running Qwen 3.8 27B, the pictures generated
with FLUX.2 Klein ([tools/readme_shots.py](tools/readme_shots.py)).

<p align="center"><i>"This month, with the holidays."</i></p>
<p align="center"><img src="docs/images/tablet-month.png" width="440" alt="A month calendar with the weather and the holidays"></p>

<p align="center"><i>"Plan my week, with the weather."</i></p>
<p align="center"><img src="docs/images/tablet-week.png" width="440" alt="A week planner with the forecast"></p>

<p align="center"><img src="docs/images/tablet-talk.png" width="440" alt="Typed questions about Mars, each answered in ink below it"></p>

<p align="center"><i>"Draw a house with a tree and the sun."</i></p>
<p align="center"><img src="docs/images/tablet-draw.png" width="440" alt="A house, a tree and the sun, drawn in pen strokes"></p>

<p align="center"><i>"Make a children's coloring page of a friendly dragon."</i></p>
<p align="center"><img src="docs/images/tablet-coloring.png" width="440" alt="A coloring page of a friendly dragon"></p>

<p align="center"><i>"Draw a koi pond, seen from above."</i></p>
<p align="center"><img src="docs/images/tablet-koi.png" width="440" alt="A koi pond seen from above, generated and drawn in pen strokes"></p>

<p align="center"><i>"Draw a forest path in autumn."</i></p>
<p align="center"><img src="docs/images/tablet-autumn.png" width="440" alt="A forest path in autumn, generated and drawn in pen strokes"></p>

<p align="center"><i>"The latest posts from r/CozyPlaces."</i></p>
<p align="center"><img src="docs/images/tablet-posts.png" width="440" alt="The newest posts from r/CozyPlaces, clipped onto the page"></p>

<p align="center"><i>"Let's play chess, Rocco. I'll be black."</i></p>
<p align="center"><img src="docs/images/tablet-chess.png" width="440" alt="A chess board from Black's side, after White's first move"></p>

<p align="center"><i>"Paste an image of the Mona Lisa."</i></p>
<p align="center"><img src="docs/images/tablet-mona.png" width="440" alt="The Mona Lisa, pasted onto the page as a picture"></p>

<p align="center"><i>"Decompose a gallery of Van Gogh's paintings."</i></p>
<p align="center"><img src="docs/images/tablet-gallery.png" width="440" alt="Six paintings by Van Gogh, drawn in pen strokes"></p>

## FAQ

**Does it change anything on my tablet?** No. Nothing is installed on the tablet. PaperDaemon reads and writes your
documents through reMarkable's cloud, the way the reMarkable desktop app does.

**Does the tablet need to be plugged in, or on the same network?** No. It only needs to sync with reMarkable's cloud.

**Is it official?** No. It signs in with the login of the reMarkable desktop app on your PC: borrowed, so the two share
it and only one runs at a time, or taken, which signs the app out. The login is kept in Windows Credential Manager.

**Where do my pages go?** To the models you choose: running on your own PC, or a service you give an API key. Only
your PC can reach PaperDaemon unless you add other addresses, and every request needs its pairing token.

**What does it build on?** The only reMarkable library it uses is [rmscene](https://github.com/ricklupton/rmscene).
Everything it ships is listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

**Do I need a tablet to try it?** No. You can install it and look around.

## License

PaperDaemon is licensed under the [Apache License 2.0](LICENSE). Copyright 2026 The PaperDaemon Authors; see
[NOTICE](NOTICE). It ships third-party components under their own licenses, listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); among them Stockfish, under the GNU GPL version 3, as a
separate program next to PaperDaemon.
