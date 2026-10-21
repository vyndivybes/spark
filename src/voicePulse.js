/// <reference types="window" />
// voicePulse.js – maps voice input to a rotating colour pulse on the UI.
// Colours are taken from the Graphify node‑type palette (organisation, division,
// project, contact, document, decision, record). If no node type is known the
// palette simply rotates on every voice command.

const palette = [
  "#3b82f6", // organisation – blue
  "#10b981", // division – green
  "#f87171", // project – red
  "#fbbf24", // contact – amber
  "#a78bfa", // document – purple
  "#f472b6", // decision – pink
  "#6b7280"  // record – gray
];
let paletteIdx = 0;

// map node‑type → palette index (optional – the app can call window.updateNodeType)
const typeToIdx = {
  organization: 0,
  division: 1,
  project: 2,
  contact: 3,
  document: 4,
  decision: 5,
  record: 6
};
let currentNodeType = null;

// ---------------------------------------------------------------------------
function setPulseColour() {
  let idx;
  if (currentNodeType && typeToIdx[currentNodeType] !== undefined) {
    idx = typeToIdx[currentNodeType];
  } else {
    idx = paletteIdx;
  }
  const hue = (idx * (360 / palette.length)) | 0;
  document.documentElement.style.setProperty(
    "--accent-hue", `hsl(${hue}deg, 70%, 55%)`);
  // round‑robin when we have no typed node
  if (!currentNodeType) {
    paletteIdx = (paletteIdx + 1) % palette.length;
  }
}

// ---------------------------------------------------------------------------
// SpeechRecognition – start listening as soon as the module loads
// ---------------------------------------------------------------------------
const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
recognition.continuous = true;
recognition.interimResults = false;
recognition.onresult = (event) => {
  // a voice command was recognised – pulse the colour
  setPulseColour();
};
recognition.start();

// ---------------------------------------------------------------------------
// Public API – the React app can tell the pulse which node type is active
// ---------------------------------------------------------------------------
window.updateNodeType = function (type) {
  currentNodeType = type;
  setPulseColour();
};