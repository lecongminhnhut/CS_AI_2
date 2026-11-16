const ink = "#292031";
const linen = "#f8e2b8";
const brass = "#d7a260";
const wine = "#933b4e";
const navy = "#365471";
const teal = "#3d706a";
const earth = "#715144";
const plum = "#695477";
const white = "#f3d8ad";

const bodies = {
  fitted: "M32 169Q37 123 56 108L85 92H115L144 108Q163 123 168 169Z",
  tailored: "M27 169L39 123Q52 107 85 93H115L151 106Q168 114 176 169Z",
  work: "M23 169L36 120Q47 106 82 93H118Q154 104 164 120L177 169Z",
  draped: "M24 169Q34 133 43 117Q60 102 84 95H114Q148 104 160 123L181 169Z",
};

// All head shapes share the ear, eye line and neck anchors so accessories fit each face.
const faces = {
  oval: "M79 58C77 43 87 29 102 29C117 29 125 41 124 55L122 70Q118 86 105 91Q91 88 83 76L79 68Q71 69 71 62Q71 55 79 58Z",
  round: "M79 58C75 42 86 29 102 29C118 29 128 43 126 56L126 69Q124 86 109 92Q94 94 83 77L79 68Q71 69 71 62Q71 55 79 58Z",
  square: "M79 58C77 44 84 31 100 29Q118 28 125 44L125 71L120 85L107 92L90 85L82 74L79 68Q71 69 71 62Q71 55 79 58Z",
  angular: "M79 58C77 43 86 30 102 29Q117 28 124 46L123 67L118 80L105 93L90 85L82 74L79 68Q71 69 71 62Q71 55 79 58Z",
};

const hair = {
  bun: {
    back: "M79 67Q67 50 76 34Q68 24 76 17Q86 7 97 16Q104 21 101 27Q116 25 125 41L126 66L119 75H84Z",
    front: "M76 58C71 42 81 27 99 26Q121 24 126 44L124 58Q115 54 111 41Q99 51 81 53L79 60Z",
    detail: "M76 25Q84 20 91 23 M84 42Q97 32 111 33",
  },
  waves: {
    back: "M73 61Q67 50 75 36Q86 20 105 23Q130 25 131 52Q129 78 138 91Q129 100 115 95Q97 103 83 94Q71 99 64 90Q74 76 73 61Z",
    front: "M76 60C69 48 77 30 93 26Q115 18 128 37Q132 45 129 57L123 64Q120 50 105 41Q94 54 82 56L79 62Z",
    detail: "M80 48Q89 33 105 33 M126 60Q125 79 131 91",
  },
  cropped: {
    front: "M76 58Q71 44 81 34Q91 23 109 26Q124 29 127 44L124 59Q121 48 116 44L90 44Q84 48 81 58Z",
    detail: "M85 38q13-7 26-4",
  },
  swept: {
    front: "M76 58Q66 48 73 35Q79 26 91 26Q106 17 117 28Q128 33 129 48L124 61Q120 48 113 42Q102 49 84 48L80 60Z",
    detail: "M79 41Q93 30 113 32",
  },
  bob: {
    back: "M69 55Q70 27 92 24Q114 17 127 35Q133 44 132 61L137 86Q129 91 116 88L83 91L65 86Z",
    front: "M74 61Q67 47 77 34Q88 20 106 24Q128 25 130 49L126 63Q121 55 120 50Q107 48 100 40Q91 53 81 54L78 62Z",
    detail: "M81 43Q88 31 101 31 M127 63l4 19",
  },
  curls: {
    front: "M76 60Q68 56 71 47Q67 39 75 35Q75 27 84 28Q89 20 98 24Q107 18 114 26Q124 23 126 33Q135 38 129 48Q130 55 124 60L120 51Q115 53 111 45Q104 51 98 45Q93 52 86 48Q84 55 79 55L79 60Z",
    detail: "M82 41q3-5 7-3 M99 34q5-6 10-1 M117 37q5-2 7 3",
  },
  braid: {
    back: "M76 67Q69 49 77 36Q86 25 101 24Q123 22 129 43L128 67Q130 78 124 89L115 91L81 82Z",
    front: "M76 58Q69 44 80 33Q93 20 111 27Q129 31 128 50L124 61Q120 49 111 42Q99 52 82 53L79 60Z",
    detail: "M82 45Q96 34 110 34",
  },
  receding: {
    front: "M79 58Q75 55 75 48Q76 37 85 34Q90 32 93 31Q91 36 86 41Q81 47 82 56Z M118 35Q128 39 128 50L124 60L121 49Z",
    detail: "M78 49q1-7 7-11",
  },
};

const braidedTail = "M123 61Q130 66 129 75Q134 81 128 89Q132 97 125 102Q127 111 118 117L111 111Q115 105 114 100Q111 94 117 88Q114 81 120 76Q117 70 123 61Z";
const hatHair = "M76 45Q99 37 125 45L127 55L124 61L120 55L117 48Q99 53 86 48L81 54L79 60L76 58Z";

// The lens centers match the pupils at (94, 61) and (114, 61).
const glasses = {
  round: ["M100 61a6 5.5 0 1 1-12 0 6 5.5 0 0 1 12 0Z M120 61a6 5.5 0 1 1-12 0 6 5.5 0 0 1 12 0Z",
    "M100 60q4-3 8 0 M88 59l-9 1"],
  square: ["M86 56q7-2 15 0l-1 8q-6 4-12 0Z M107 56q7-2 15 0l-2 8q-6 4-12 0Z",
    "M101 58q3-2 6 0 M86 58l-7 2"],
  monocle: ["M120 61a6 6 0 1 1-12 0 6 6 0 0 1 12 0Z", "M119 65Q122 79 119 92"],
};

const headwear = {
  chef: [
    "M79 52L78 40Q69 38 69 30Q70 22 79 21Q83 12 94 14Q104 7 114 14Q122 14 126 22Q136 25 134 33Q133 39 126 42L125 52Q103 47 79 52Z",
    "M79 45Q102 40 126 45 M89 25q5-4 10-3 M116 24q4 4 3 11",
  ],
  courier: [
    "M76 48Q77 33 90 28Q109 21 123 34Q128 40 129 48Q117 53 103 50Q90 47 76 48Z",
    "M89 47Q109 43 128 47 M102 29q11 2 15 14",
    "M92 47Q117 49 139 44Q137 52 126 54Q108 54 92 47Z",
  ],
  fedora: [
    "M76 46L82 29Q85 21 94 24L103 29Q113 22 120 25Q125 30 129 44Q145 44 146 49Q144 56 110 56Q81 55 63 49Q60 45 76 46Z",
    "M77 42Q100 47 128 41 M92 29l10 4",
    "M75 45Q104 50 129 44L128 49Q100 54 75 48Z",
  ],
  helmet: [
    "M74 49L77 43Q78 25 94 22L97 18H107L110 22Q127 25 130 44L137 47L136 52Q105 49 74 54Z",
    "M78 44Q105 41 130 44 M97 23l-3 13 M109 23l4 13",
    "M74 49Q106 44 137 47L136 52Q105 49 74 54Z",
  ],
  guard: [
    "M72 44L78 31L92 23Q104 19 116 23L127 30L134 43Q125 52 104 52Q82 51 72 44Z",
    "M77 43Q103 47 130 42",
    "M88 49Q110 48 137 44Q133 54 119 56Q101 56 88 49Z",
  ],
  beret: [
    "M76 50Q67 45 71 36Q80 22 102 22Q124 21 130 34Q134 42 124 48Q98 45 76 50Z",
    "M77 45Q102 39 124 44 M91 28q10-4 20-2",
  ],
  sailor: [
    "M75 49L77 36Q86 24 102 23Q122 23 130 37L131 48Q103 44 75 49Z",
    "M77 39Q103 35 129 40",
    "M75 45Q103 40 131 43V49Q104 45 75 51Z",
  ],
  explorer: [
    "M73 44Q78 29 93 25Q113 20 125 32L130 44Q148 46 148 51Q144 57 112 55Q80 55 58 50Q62 46 73 44Z",
    "M74 43Q102 47 130 43 M91 30q11-5 20-2",
    "M74 43Q102 47 130 43L131 48Q103 51 72 47Z",
  ],
  wrap: [
    "M72 45Q78 27 101 24Q123 24 129 46L125 53Q115 46 104 41Q92 50 76 53L74 64L65 73L67 56Z",
    "M72 46Q89 34 110 31 M83 44q13-8 28-9",
  ],
  headset: [
    "M73 57V47Q75 24 101 21Q127 22 131 47V57H126V47Q122 27 101 27Q81 28 78 47V57Z",
    "M75 48Q80 22 101 24Q123 24 129 47",
    "M71 54Q76 52 81 55L81 68Q78 73 72 70L69 65V57Z M125 54Q129 52 133 55V66Q130 71 124 69Z",
  ],
};

// Each occupation has its own outfit, including the shape and seams of the garment.
const designs = {
  Archivist: {
    hair: "bun", face: "angular", eyewear: "round", body: "fitted", coat: teal,
    layers: [[linen, "M57 113L83 96L102 111L116 94L145 113L138 169H64Z"],
      [teal, "M65 107L80 101L102 118L123 101L137 108L128 169H76Z"],
      [null, "M102 119V169 M94 133h2 M94 144h2 M94 155h2 M77 128h16 M113 128h15"]],
  },
  Baker: {
    hair: "curls", face: "round", beard: true, hat: "chef", hatColor: white, body: "work", coat: linen,
    layers: [[wine, "M79 97L100 109L119 95L120 104L100 122L78 104Z"],
      [white, "M48 169L57 117L67 112L68 132H133L136 110L146 116L153 169Z"],
      [null, "M81 145h35v15H81z M116 111h2 M117 123h2"]],
  },
  Courier: {
    hair: "braid", face: "round", hat: "courier", body: "fitted", coat: navy,
    layers: [[wine, "M52 112l6-6 80 63h-20z M81 98l6-5 14 10 14-10 9 9-10 14-14-9-13 9z"],
      [brass, "M127 113l12 2-2 12-12-2z"], [null, "M99 118v10 M52 132l13 8 M144 140l12-5"]],
  },
  Detective: {
    hair: "swept", face: "square", hat: "fedora", body: "tailored", coat: earth,
    layers: [[navy, "M81 102l20 8 21-10-10 69H88z"],
      [linen, "M83 99l18 9-7 11z M119 97l-18 11 13 10z"],
      [brass, "M59 109l20-13 18 73-29-32 5-10-17-7z M143 105l-24-10-9 74 28-34-7-11 16-9z"],
      [null, "M40 124l16-6 M148 121l14 6 M69 153h11"]],
  },
  Engineer: {
    hair: "cropped", face: "angular", hat: "helmet", hatColor: brass, eyewear: "square", body: "work", coat: navy,
    layers: [[brass, "M49 113l15-9 15 65H57z M132 104l16 9-8 56h-24z"],
      [linen, "M51 126l16-6 3 12-17 6z M129 120l17 6-2 12-18-6z"],
      [null, "M100 111v58 M85 127H72 M114 127h15"]],
  },
  Florist: {
    hair: "waves", face: "oval", body: "draped", coat: plum,
    layers: [[teal, "M57 111l12-8 15 23h36l15-23 12 8-11 58H68z"],
      [linen, "M82 98q20 14 38-1l8 6q-5 18-27 17-18 0-26-15z"],
      [brass, "M101 140q-13-10-9-15 7-4 10 5 3-9 10-5 4 5-11 15z"],
      [null, "M101 139v18 M101 150l-10-6 M101 152l9-7"]],
  },
  Guard: {
    hair: "cropped", face: "square", hat: "guard", body: "work", coat: navy,
    headDetail: "M99 30h12l-6 10z",
    layers: [[wine, "M80 96l19 10 19-12 5 9-10 14-13-7-15 7-8-12z"],
      [brass, "M39 116l25-12 6 9-23 13z M137 104l23 10-7 11-22-12z M126 120l9 3v10l-9 6-9-6v-10z"],
      [null, "M100 113v56 M97 130h5 M97 143h5 M97 156h5"]],
  },
  Historian: {
    hair: "receding", face: "angular", eyewear: "monocle", body: "tailored", coat: earth,
    layers: [[linen, "M77 101l23 10 19-11 13 9-29 50z"],
      [plum, "M55 111l27-16-3 18 24 56H85l-21-43 7-6z M146 109l-26-14 4 17-21 57h14l21-44-6-5z"],
      [wine, "M96 113h9l7 38-10 12-9-12z"], [null, "M127 143l17-3 M128 149l15-3"]],
  },
  Illustrator: {
    hair: "curls", face: "round", hat: "beret", body: "draped", coat: wine,
    layers: [[linen, "M76 97q23 14 46-3l7 12q-29 19-58 1z"],
      [teal, "M53 112l8-6 19 32 44-3 11-31 9 6-4 59H59z"],
      [brass, "M84 146l8-5 4 4-7 6z M111 149l10 1 3 5-10 2z"],
      [wine, "M72 154l7-3 7 5-10 3z"]],
  },
  Journalist: {
    hair: "swept", face: "angular", hat: "fedora", body: "tailored", coat: navy,
    layers: [[linen, "M79 97L102 109L122 97L113 169H88Z"],
      [earth, "M55 109L82 94L78 113L98 168L70 136L77 126L57 118Z M148 110L120 94L122 115L111 169L137 136L129 125L150 119Z"],
      [wine, "M96 110h11l-2 11 7 30-11 10-8-11 5-29z"],
      [brass, "M127 132l17-4 3 11-17 4z"]],
  },
  Keeper: {
    hair: "waves", face: "square", beard: true, body: "draped", coat: earth,
    layers: [[teal, "M44 117q21-18 41-24l15 13 20-13q21 4 43 24l-46 28-17-20-18 20z"],
      [wine, "M82 94l18 11 18-11 8 12-25 22-27-21z"],
      [brass, "M95 119h10v11H95Z"], [null, "M54 126l21 13 M146 126l-20 13"]],
  },
  Librarian: {
    hair: "bob", face: "round", eyewear: "round", body: "fitted", coat: plum,
    layers: [[linen, "M78 99l23 12 21-12 7 8-17 22-11-13-10 13-19-22z"],
      [wine, "M101 114q-22-14-17-2 3 10 17 5 15 5 17-5 4-11-17 2z"],
      [null, "M100 128v41 M94 133h3 M94 145h3 M94 156h3 M56 142h22 M124 142h22"]],
  },
  Mechanic: {
    hair: "cropped", face: "square", beard: true, hat: "courier", body: "work", coat: earth,
    layers: [[teal, "M51 113l13-7 10 26h54l9-28 13 8-11 57H59z"],
      [brass, "M63 126h12v9H63z M128 126h12v9h-12z"],
      [navy, "M80 144h42v18H80z"], [null, "M91 149h19 M44 134l8 4 M149 138l9-5"]],
  },
  Navigator: {
    hair: "waves", face: "oval", hat: "sailor", hatColor: linen, body: "tailored", coat: navy,
    headDetail: "M96 35q6-3 12 0l-2 6h-8z",
    layers: [[linen, "M65 102l19-8 17 20 15-20 22 8-15 27-22 17-23-17z"],
      [teal, "M73 103l10-4 18 21 17-21 11 4-10 19-18 18-17-17z"],
      [wine, "M101 130l-12 19 12-5 12 7z"]],
  },
  Operator: {
    hair: "bob", face: "angular", hat: "headset", hatColor: brass, body: "fitted", coat: plum,
    headDetail: "M129 67q-6 10-17 7l-1 3q14 4 20-9z",
    layers: [[navy, "M79 95l22 13 18-13 8 17-16 17h-19l-20-17z"],
      [brass, "M48 126l20-12 4 7-19 12z M132 117l22 10-4 8-21-10z"],
      [null, "M102 130v39"]],
  },
  Photographer: {
    hair: "swept", face: "oval", hat: "beret", body: "fitted", coat: teal,
    layers: [[wine, "M78 94l23 10 18-10q8 10 4 20l-33 10-14-5z"],
      [earth, "M55 108l8-4 61 65h-13z M135 105l8 4-24 34-5-6z"],
      [navy, "M92 141h15l4-6h16l3 6h10v22H92z"],
      [brass, "M126 152a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"]],
  },
  Restorer: {
    hair: "bun", face: "angular", eyewear: "square", body: "draped", coat: wine,
    layers: [[linen, "M78 96l23 15 18-15 11 12-12 15-17-7-16 7-16-12z"],
      [earth, "M62 107l8-4 17 26h30l13-26 9 5-5 61H68z"],
      [teal, "M83 142h36v17H83z"], [null, "M90 142l-2-11 M96 142l3-14 M111 142l9-10"]],
  },
  Sculptor: {
    hair: "braid", face: "square", hat: "wrap", body: "work", coat: plum,
    layers: [[linen, "M75 99l26 12 18-15 8 5q-8 25-26 25-17 0-31-22z"],
      [earth, "M56 113l10-6 9 29h48l11-29 10 5-5 57H62z"],
      [brass, "M66 131h10v8H66z M124 131h10v8h-10z"],
      [linen, "M85 150l14-5 5 4-14 7z M110 156l8-4 5 4-8 3z"]],
  },
  Tailor: {
    hair: "receding", face: "angular", eyewear: "round", body: "fitted", coat: wine,
    layers: [[linen, "M70 102l16-6 15 14 16-15 17 8-16 66H87z"],
      [navy, "M65 105l14-6 22 32 18-33 15 7-12 64H79z"],
      [brass, "M82 96l8 4-4 55-8 1z M111 100l8-4 4 57h-8z"],
      [null, "M83 111h5 M82 127h4 M80 143h5 M114 111h5 M116 127h5 M118 143h4 M101 133v36"]],
  },
  Technician: {
    hair: "bob", face: "square", eyewear: "square", body: "work", coat: teal,
    layers: [[navy, "M35 120l40-21 26 11 23-11 41 22-19 14-29-12H84l-31 12z"],
      [linen, "M77 99l11-5 13 13 17-13 9 6-10 14h-32z"], [brass, "M122 134h20v11h-20z"],
      [null, "M101 114v55 M64 145l16 1 M127 138h11"]],
  },
  Underwriter: {
    hair: "bun", face: "oval", body: "tailored", coat: plum,
    layers: [[linen, "M79 99l22 14 22-14-4 28-18 28-20-28z"],
      [navy, "M60 108l25-13-4 19 20 41 20-40-4-20 27 12-13 19 3 8-33 34-32-35 3-7z"],
      [wine, "M90 112l11 4 13-5-7 11 4 16-10 14-8-13 4-17z"],
      [brass, "M125 138l14-4 2 6-14 5z"]],
  },
  Violinist: {
    hair: "waves", face: "oval", body: "draped", coat: wine,
    layers: [[plum, "M36 128q18-20 47-33l19 26 19-25q34 13 48 32l-29 20-16 21H75L59 148z"],
      [linen, "M80 96l22 18 17-18 11 7-12 24-16-8-15 8-19-24z"],
      [brass, "M99 121l3-5 5 5-4 8z"], [null, "M56 126l26 30 M146 128l-23 26"]],
  },
  Watchmaker: {
    hair: "receding", face: "round", eyewear: "monocle", beard: true, body: "fitted", coat: navy,
    layers: [[linen, "M77 100l24 12 19-15 13 9-19 29H87z"],
      [earth, "M63 106l15-5 24 33 19-35 16 8-12 62H76z"],
      [brass, "M103 139q8 17 24 9l1 4q-17 9-27-11z"], [null, "M101 135v34 M122 141h12 M56 134l14 6"]],
  },
  Writer: {
    hair: "swept", face: "oval", eyewear: "round", body: "draped", coat: earth,
    layers: [[linen, "M77 97l25 12 17-13 9 6-13 20-13-9-13 11-19-19z"],
      [teal, "M74 108q15 14 43 3l7 9-15 12 9 37-15-7-8-32-23-12z"],
      [null, "M55 127l18 23 M145 125l-19 23"]],
  },
  Zoologist: {
    hair: "braid", face: "round", hat: "explorer", hatColor: brass, body: "work", coat: earth,
    layers: [[teal, "M49 112l28-13 24 24 23-24 29 13-13 57H60z"],
      [linen, "M83 96l18 12 18-12 6 9-24 20-24-20z"],
      [brass, "M68 134h25v16H68z M112 134h24v16h-24z"],
      [null, "M101 126v43 M68 139h25 M112 139h24"]],
  },
};

const skinTones = ["#f2c895", "#b97957", "#e3a873", "#d49870", "#f3cea8", "#99614c"];
const hairTones = ["#533344", "#4a3032", "#813e36", "#574354", "#845532", "#3f333c"];

function draw(ctx, shape, fill, line = 1.7, stroke = ink) {
  if (!shape) return;
  const path = new Path2D(shape);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill(path);
  }
  ctx.strokeStyle = stroke;
  ctx.lineWidth = line;
  ctx.stroke(path);
}

function drawHalo(ctx) {
  const arc = "M43 97A59 59 0 0 1 157 97";
  draw(ctx, arc, null, 1.35, "#5d3a3859");
  draw(ctx, "M36 87A65 65 0 0 1 164 87 M30 74l4 5-4 5-4-5z M170 74l4 5-4 5-4-5z",
    null, 1, "#8a5d426b");
}

export function makePortrait(card, index) {
  const canvas = document.createElement("canvas");
  canvas.className = "portrait-illustration";
  canvas.width = 400;
  canvas.height = 336;
  canvas.setAttribute("aria-hidden", "true");
  const ctx = canvas.getContext("2d");
  if (!ctx) return canvas;
  ctx.scale(2, 2);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  drawHalo(ctx);

  const design = designs[card.profession] ?? designs.Archivist;
  const skin = skinTones[index % skinTones.length];
  const hairColor = hairTones[(index + Math.floor(index / 4)) % hairTones.length];
  const hairstyle = hair[design.hair];
  const wearsHat = design.hat && design.hat !== "headset";
  if (index % 4 >= 2) {
    ctx.translate(200, 0);
    ctx.scale(-1, 1);
  }
  if (!wearsHat) draw(ctx, hairstyle.back, hairColor);
  draw(ctx, bodies[design.body], design.coat, 2.3);
  draw(ctx, "M85 78H117L115 94Q116 98 118 100L102 111L83 100Q87 94 85 78Z", skin);
  draw(ctx, "M87 81L115 80L114 94L103 101L88 92Z", "#793f3438", 1, "transparent");
  for (const [fill, shape] of design.layers) draw(ctx, shape, fill, 1.45);
  if (design.hair === "braid") {
    draw(ctx, braidedTail, hairColor);
    draw(ctx, "M121 76l6 4 M118 88l8 5 M115 100l7 4", null, 1, "#f8e2b860");
    draw(ctx, "M112 108l9 4-3 5-7-5z", brass, 1.15);
  }
  const face = faces[design.face];
  draw(ctx, face, skin, 2.15);
  ctx.save();
  ctx.clip(new Path2D(face));
  draw(ctx, "M122 44Q116 53 118 67Q118 83 104 93L127 94L134 60Z", "#793f3438", 1, "transparent");
  draw(ctx, "M85 69q5-2 9 1l-4 2z M111 70q4-2 8-1l-4 3z", "#a55d483f", 1, "transparent");
  ctx.restore();
  draw(ctx, "M77 61q-4-1-3 3", null, 1, "#793f3490");
  draw(ctx, wearsHat ? hatHair : hairstyle.front, hairColor, 1.7);
  if (!wearsHat) draw(ctx, hairstyle.detail, null, 1.1, "#f8e2b860");
  if (design.beard) {
    draw(ctx, "M82 69Q88 75 94 74L100 72L106 73L112 71L122 70Q120 85 108 94Q94 94 86 82Z", hairColor, 1.6);
    draw(ctx, "M96 78Q104 74 113 77Q110 83 103 83Q99 83 96 78Z", skin, 1);
    draw(ctx, "M100 79q4 1 8-1", null, 1);
  } else {
    draw(ctx, "M98 78Q104 80 109 77", null, 1.3);
    draw(ctx, "M102 83h4", null, 1, "#793f3490");
  }
  draw(ctx, "M89 57q4-3 8-1 M110 56q4-2 8 0 M103 61l-2 8 5 1", null, 1.35);
  draw(ctx, "M94 61h.2 M114 61h.2", null, 2.35);
  if (design.eyewear) {
    const [lenses, frame] = glasses[design.eyewear];
    draw(ctx, lenses, "#fff7dd26", 1.35);
    draw(ctx, frame, null, 1.25);
  }
  if (design.hat) {
    const [crown, seams, trim] = headwear[design.hat];
    draw(ctx, crown, design.hatColor ?? design.coat, 1.8);
    draw(ctx, trim, "#29203144", 1.15);
    draw(ctx, seams, null, 1, "#2920319c");
  }
  draw(ctx, design.headDetail, brass, 1.25);
  return canvas;
}
