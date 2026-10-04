# Flow: brand notes

Flow is a family of apps, each named Flow and its subject: Flow ITR, Flow
Health, Flow Learn, Flow Create. These notes keep them looking and reading like
one family. Flow ITR is the first of them, and the conventions below are its.

## Names

- The family is **Flow**. An app is **Flow ITR**: two words, Flow first. Not
  "FlowITR", "Flow-ITR" or "ITR Flow".
- The subject keeps its own case. ITR is an abbreviation, so it is in capitals;
  the others are words: Health, Learn, Create.
- In an app's own text, name the app in full wherever the sentence means it:
  "Flow ITR files nothing". Flow on its own means the family.
- Repositories and folders are in lower case with a hyphen: `flow-itr`,
  `flow-health`.

## The mark

A rounded square, 32 by 32 with corners of radius 8, and on it a white "F"
drawn as a single stroke (3.2 wide, round ends) with a dot at the end of its
bar. The source is [web/logo.svg](../web/logo.svg).

The mark is the same for every app. Only two colours change: the tile, and the
dot, which is a light tint of the tile's hue. At favicon size the colour is what
tells two Flow apps apart, so no app adds anything else to the mark.

## Colours

| App | Tile | Dot | White F on the tile | Dot on the tile |
|---|---|---|---|---|
| Flow ITR | `#0B57D0` | `#A9C7FF` | 6.4:1 | 3.7:1 |
| Flow Health (proposed) | `#0B7A55` | `#9EE6C7` | 5.3:1 | 3.7:1 |
| Flow Learn (proposed) | `#6A3FD0` | `#CDBBFF` | 6.5:1 | 3.8:1 |
| Flow Create (proposed) | `#C2410C` | `#FFC9A8` | 5.2:1 | 3.5:1 |

A further app takes a hue none of these uses, dark enough for the white F to
stand at 4.5:1 or more, with a dot at 3:1 or more. Inside each app the tile's
colour is the accent: in Flow ITR it is the page's blue (`--blue` in
[web/styles.css](../web/styles.css)).

## The lockup

The mark, then **Flow** in the family's weight (Figtree, 700), then the app's
subject in 600 and in the app's colour, after an ordinary space (so the name
copies and searches as "Flow ITR"):

```html
<span class="brand-name">Flow <span class="brand-app">ITR</span></span>
```

The header of every Flow app uses it, and it leads to the app's Home page. The
browser tab reads "the page · Flow ITR".

## The rest of the family's look

The same typefaces (Figtree, and IBM Plex Mono for paths and figures that must
line up), the same colour tokens and dark theme, and the same way of writing:
plain, specific, saying what happened and what to do next, with no
exclamation marks.

## To settle before the second app

These are fine for one app and would collide with two:

- **The data folder.** Done for Flow ITR: it keeps everything personal in
  `Flow/ITR` in your user folder (or wherever `FLOW_HOME` points), and moved
  its files there from the `flow` folder earlier versions used. Each further
  app takes `Flow/<App>` beside it: `Flow/Health`, `Flow/Learn`.
- **The port.** Flow ITR serves on `127.0.0.1:8787`. Each app needs its own port
  to run beside the others.
- **Google Drive.** "Put on Google Drive" already uses `Flow/ITR/<return>` on
  the Drive, so other apps can sit beside it under `Flow/`.
