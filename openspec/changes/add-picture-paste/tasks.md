## 1. Pasted pictures

- [x] 1.1 The step field: `paste` on image and web_picture steps (`steps.FIELDS`, taken only as a plain true)
- [x] 1.2 The host: `_paste_into` puts the picture on as an image block; image steps (`_run_images`) and web_picture
  steps (`t_fetch`) use it when the step says paste
- [x] 1.3 The brief: draw is a sketch; image and web_picture drawn in strokes or pasted as they are
- [x] 1.4 Tests: a pasted picture goes on as a picture with no strokes; the field is declared and parsed
- [x] 1.6 Sketches on one grid: icon parts (`_part_paths`), an icon drawn with the figure joins it (`t_element`),
  a figure drawn again keeps its box (`_draw_figure`, `JOB.looking`); no `image()` in a sketch step; tests
- [x] 1.7 Whether a look at the drawing (`RM_HOST_DRAW_LOOKS`) is needed, measured live: after 1.6, six sketch
  requests (a house with a tree and the sun, a bicycle, a sailboat with a seagull, a snowman in a hat, a rocket and
  three stars, a cat by a window) all came out readable with no look, where the house had failed three of three
  before; the look stays off
- [ ] 1.5 A real run: "Paste an image of the Mona Lisa" pasted, a sketch drawn from shapes, a generated picture
  decomposed (Qwen and Klein on the real tablet); the README's page made again (the Mona Lisa done: Qwen pasted it
  and the README's page was made again; a sketch and a generated picture still to run)
