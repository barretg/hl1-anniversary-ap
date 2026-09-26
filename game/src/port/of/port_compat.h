// Helpers halflife-op4-updated takes from halflife-updated that this SDK lacks,
// so the ported Opposing Force sources compile unchanged where they can.
#pragma once

// Included after the file's own headers: this SDK's util.h has no include
// guard, so this header includes nothing of the SDK's but the guarded
// weaponinfo.h.

#include "weaponinfo.h"

#ifndef V_min
#define V_min(a, b) (((a) < (b)) ? (a) : (b))
#define V_max(a, b) (((a) > (b)) ? (a) : (b))
#endif

// Singleplayer: the one player, or null before they have joined.
inline CBaseEntity* UTIL_GetLocalPlayer()
{
	return UTIL_PlayerByIndex(1);
}

// Half-Life keeps this file-local in barney.cpp; the OF allies share it.
inline BOOL IsFacing(entvars_t* pevTest, const Vector& reference)
{
	Vector vecDir = (reference - pevTest->origin);
	vecDir.z = 0;
	vecDir = vecDir.Normalize();
	Vector forward, angle;
	angle = pevTest->v_angle;
	angle.x = 0;
	UTIL_MakeVectorsPrivate(angle, forward, NULL, NULL);
	// He's facing me, he meant it
	if (DotProduct(forward, vecDir) > 0.96) // +/- 15 degrees or so
	{
		return TRUE;
	}
	return FALSE;
}

// pev->waterlevel values.
constexpr int WATERLEVEL_DRY = 0;
constexpr int WATERLEVEL_FEET = 1;
constexpr int WATERLEVEL_WAIST = 2;
constexpr int WATERLEVEL_HEAD = 3;

// halflife-updated's range-for over the entities with a classname or
// targetname: `for (auto p : UTIL_FindEntitiesByClassname("x"))`.
template <typename T, bool ByTargetname>
class CPortEntityRange
{
public:
	class iterator
	{
	public:
		iterator(const char* name, T* entity) : m_Name(name), m_Entity(entity) {}
		T* operator*() const { return m_Entity; }
		bool operator!=(const iterator& other) const { return m_Entity != other.m_Entity; }
		iterator& operator++()
		{
			m_Entity = Next(m_Name, m_Entity);
			return *this;
		}

	private:
		const char* m_Name;
		T* m_Entity;
	};

	explicit CPortEntityRange(const char* name, T* start = nullptr) : m_Name(name), m_Start(start) {}
	iterator begin() const { return iterator(m_Name, Next(m_Name, m_Start)); }
	iterator end() const { return iterator(m_Name, nullptr); }

private:
	static T* Next(const char* name, T* after)
	{
		CBaseEntity* next = ByTargetname
			? UTIL_FindEntityByTargetname(after, name)
			: UTIL_FindEntityByClassname(after, name);
		return static_cast<T*>(next);
	}

	const char* m_Name;
	T* m_Start;
};

template <typename T = CBaseEntity>
inline CPortEntityRange<T, false> UTIL_FindEntitiesByClassname(const char* name, T* start = nullptr)
{
	return CPortEntityRange<T, false>(name, start);
}

template <typename T = CBaseEntity>
inline CPortEntityRange<T, true> UTIL_FindEntitiesByTargetname(const char* name, T* start = nullptr)
{
	return CPortEntityRange<T, true>(name, start);
}

inline void WRITE_COORD_VECTOR(const Vector& vec)
{
	WRITE_COORD(vec.x);
	WRITE_COORD(vec.y);
	WRITE_COORD(vec.z);
}

// Singleplayer only: capture the flag never runs.
inline bool UTIL_IsMultiplayer()
{
	return gpGlobals->maxClients > 1;
}

inline bool UTIL_IsCTF()
{
	return false;
}
