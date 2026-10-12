// Standard headers first: the SDK's min/max macros break <cmath>.
#include <cmath>
#include <map>
#include <string>

#include "hud.h"
#include "cl_util.h"
#include "parsemsg.h"
#include "com_model.h"
#include "cl_entity.h"
#include "triangleapi.h"

#include "ap_labels.h"

namespace {

// How far away a label is still drawn, and how high over the entity's origin.
// A monster's origin is at its feet; a pickup's is on the floor too.
constexpr float kMaxDistance = 2048.0f;
constexpr float kMonsterRise = 80.0f;
constexpr float kItemRise = 24.0f;

std::map<int, std::string> g_labels;

int __MsgFunc_APLabel(const char* pszName, int iSize, void* pbuf)
{
	BEGIN_READ(pbuf, iSize);
	const int index = READ_SHORT();
	const std::string text = READ_STRING();
	if (index == 0)
		g_labels.clear();
	else if (text.empty())
		g_labels.erase(index);
	else
		g_labels[index] = text;
	return 1;
}

}  // namespace

void APLabels_Init()
{
	gEngfuncs.pfnHookUserMsg(const_cast<char*>("APLabel"), __MsgFunc_APLabel);
}

void APLabels_VidInit()
{
	g_labels.clear();
}

void APLabels_Frame()
{
	if (g_labels.empty())
		return;
	cl_entity_t* local = gEngfuncs.GetLocalPlayer();
	if (local == nullptr)
		return;
	for (const auto& entry : g_labels)
	{
		cl_entity_t* ent = gEngfuncs.GetEntityByIndex(entry.first);
		// Not in this frame's update: out of the PVS, or gone.
		if (ent == nullptr || ent->curstate.messagenum < local->curstate.messagenum)
			continue;
		float world[3] = {ent->origin[0], ent->origin[1], ent->origin[2]};
		const float dx = world[0] - local->origin[0];
		const float dy = world[1] - local->origin[1];
		const float dz = world[2] - local->origin[2];
		if (std::sqrt(dx * dx + dy * dy + dz * dz) > kMaxDistance)
			continue;
		// A monster moves; a pickup is a toss or none.
		world[2] += ent->curstate.movetype == MOVETYPE_STEP ? kMonsterRise : kItemRise;
		float screen[3];
		if (gEngfuncs.pTriAPI->WorldToScreen(world, screen))
			continue;  // behind the view
		const int x = static_cast<int>(XPROJECT(screen[0]));
		const int y = static_cast<int>(YPROJECT(screen[1]));
		if (x < 0 || y < 0 || x >= ScreenWidth || y >= ScreenHeight)
			continue;
		int width = 0, height = 0;
		gEngfuncs.pfnDrawConsoleStringLen(entry.second.c_str(), &width, &height);
		gEngfuncs.pfnDrawSetTextColor(1.0f, 0.8f, 0.2f);
		gEngfuncs.pfnDrawConsoleString(x - width / 2, y - height,
		                               const_cast<char*>(entry.second.c_str()));
	}
}
