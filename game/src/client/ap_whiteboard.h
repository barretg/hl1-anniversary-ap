// The lobby's whiteboard, redrawn at random each time the lobby loads.
//
// The board is the stock `poster15` from halflife.wad, so the map itself cannot
// vary it: a brush texture is fixed at compile time, and GoldSrc's texture
// animation tops out at ten frames that cycle on their own. Instead the client
// replaces the pixels of the engine's own GL texture once the level is up, which
// keeps the world lighting, placement and decals exactly as the map has them.
#pragma once

// A level connect is starting. Called from HUD_VidInit.
void APWhiteboard_VidInit();

// Called every HUD frame. Does its work on the first one after a connect.
void APWhiteboard_Frame();
