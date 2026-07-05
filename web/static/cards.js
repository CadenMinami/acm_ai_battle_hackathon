// web/static/cards.js
// Shared card-name -> icon map for the canvas renderer (viewer.js). These
// are the 10 names that can appear in a default-deck match (confirmed
// against engine/src/clasher/player.py's default deck, plus the two tower
// entity types). Anything not in this map falls back to a generic icon
// instead of breaking the renderer, in case the deck ever changes.
const CARD_ICONS = {
  Knight: "⚔️",
  Archer: "🏹",
  Giant: "👹",
  Minions: "🦇",
  Musketeer: "🔫",
  BabyDragon: "🐉",
  Balloon: "🎈",
  Wizard: "🧙",
  Tower: "🗼",
  KingTower: "👑",
};

const CARD_ICON_FALLBACK = "❔";

function getCardIcon(cardName) {
  return CARD_ICONS[cardName] || CARD_ICON_FALLBACK;
}
