// `ap_labels`: each tagged check's name drawn above it in the world, for telling
// one scientist, guard or pickup from the next while curating.
//
// The server sends `APLabel` (entity index, text; empty text removes one, index
// 0 clears all). The client keeps the list and draws each label over its
// entity's current position every HUD frame, through walls, while the entity
// is in this frame's update (in the PVS).
#pragma once

// Hooks the message. Called from CHud::Init.
void APLabels_Init();

// A level connect is starting: entity indices are about to mean something else.
void APLabels_VidInit();

// Called every HUD frame.
void APLabels_Frame();
