// The hlap Valve Server Plugin for Half-Life: Source.
//
// Phase 0 spike: proves the plugin loads into HL:S, receives GameFrame, and can
// refuse a weapon pickup by swapping CHalfLife1::CanHavePlayerItem in the game's
// own vftable. Console:
//
//   hlap_refuse <classname>   refuse that weapon from now on
//   hlap_refuse               stop refusing
//   hlap_status               print what the plugin has hooked
#include <cstdio>
#include <cstring>

#include "sdk.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
// winuser.h would turn edict_t::GetClassName into GetClassNameA.
#undef GetClassName

#include "generated/hls_vtables.h"
#include "log.h"
#include "vtable_hook.h"

class CBasePlayer;
class CBaseCombatWeapon;

namespace {

IVEngineServer *g_engine = nullptr;
IServerGameEnts *g_ents = nullptr;

void **g_rules_vft = nullptr;
void *g_orig_can_have = nullptr;
char g_refuse[64] = "";
unsigned g_frames = 0;
unsigned g_refusals = 0;

const char *ClassnameOf(CBaseCombatWeapon *weapon) {
    if (!weapon || !g_ents) return "";
    edict_t *e = g_ents->BaseEntityToEdict(reinterpret_cast<CBaseEntity *>(weapon));
    return e ? e->GetClassName() : "";
}

// thiscall, reached through __fastcall: `this` in ecx, edx unused.
using CanHaveFn = bool(__thiscall *)(void *, CBasePlayer *, CBaseCombatWeapon *);

bool __fastcall CanHavePlayerItem(void *self, void * /*edx*/, CBasePlayer *player,
                                  CBaseCombatWeapon *weapon) {
    const char *cls = ClassnameOf(weapon);
    hlap::Log("CanHavePlayerItem %s", cls);
    if (g_refuse[0] && std::strcmp(cls, g_refuse) == 0) {
        ++g_refusals;
        hlap::Log("refused %s (%u)", cls, g_refusals);
        return false;
    }
    return reinterpret_cast<CanHaveFn>(g_orig_can_have)(self, player, weapon);
}

void InstallHooks(CreateInterfaceFn game_factory) {
    if (g_orig_can_have) return;
    HMODULE mod = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                           GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       reinterpret_cast<LPCSTR>(game_factory), &mod);
    char name[MAX_PATH] = {};
    GetModuleFileNameA(mod, name, MAX_PATH);
    hlap::Log("game factory %p in %s; scanning for CHalfLife1", reinterpret_cast<void *>(game_factory), name);
    g_rules_vft = hlap::FindVftable(reinterpret_cast<const void *>(game_factory), "CHalfLife1");
    if (!g_rules_vft) {
        hlap::Log("CHalfLife1 vftable not found; pickup refusal is off");
        return;
    }
    g_orig_can_have = hlap::PatchSlot(g_rules_vft, kSlot_CHalfLife1_CanHavePlayerItem,
                                      reinterpret_cast<void *>(&CanHavePlayerItem));
    hlap::Log("CHalfLife1 vftable at %p, CanHavePlayerItem slot %d hooked (was %p)",
        static_cast<void *>(g_rules_vft), kSlot_CHalfLife1_CanHavePlayerItem, g_orig_can_have);
}

void RemoveHooks() {
    if (g_rules_vft && g_orig_can_have)
        hlap::PatchSlot(g_rules_vft, kSlot_CHalfLife1_CanHavePlayerItem, g_orig_can_have);
    g_orig_can_have = nullptr;
}

class Plugin : public IServerPluginCallbacks {
public:
    bool Load(CreateInterfaceFn engine_factory, CreateInterfaceFn game_factory) override {
        hlap::Log("Load entered");
        g_engine = static_cast<IVEngineServer *>(
            engine_factory(INTERFACEVERSION_VENGINESERVER, nullptr));
        g_ents = static_cast<IServerGameEnts *>(
            game_factory(INTERFACEVERSION_SERVERGAMEENTS, nullptr));
        if (!g_engine || !g_ents) {
            hlap::Log("missing %s or %s; not loading", INTERFACEVERSION_VENGINESERVER,
                    INTERFACEVERSION_SERVERGAMEENTS);
            return false;
        }
        hlap::Log("loaded");
        InstallHooks(game_factory);
        return true;
    }
    void Unload() override {
        hlap::Log("Unload");
        RemoveHooks();
    }
    void Pause() override {}
    void UnPause() override {}
    const char *GetPluginDescription() override { return "hlap: Archipelago for Half-Life: Source"; }
    void LevelInit(const char *map) override { hlap::Log("LevelInit %s", map); }
    void ServerActivate(edict_t *, int, int) override { hlap::Log("ServerActivate"); }
    void GameFrame(bool simulating) override {
        if (simulating && ++g_frames % 1000 == 0) hlap::Log("GameFrame %u", g_frames);
    }
    void LevelShutdown() override { hlap::Log("LevelShutdown"); }
    void ClientActive(edict_t *) override {}
    void ClientDisconnect(edict_t *) override {}
    void ClientPutInServer(edict_t *, const char *) override { hlap::Log("ClientPutInServer"); }
    void SetCommandClient(int) override {}
    void ClientSettingsChanged(edict_t *) override {}
    PLUGIN_RESULT ClientConnect(bool *, edict_t *, const char *, const char *, char *, int) override {
        return PLUGIN_CONTINUE;
    }
    PLUGIN_RESULT ClientCommand(edict_t *, const CCommand &args) override {
        if (args.ArgC() < 1) return PLUGIN_CONTINUE;
        if (std::strcmp(args.Arg(0), "hlap_refuse") == 0) {
            std::snprintf(g_refuse, sizeof g_refuse, "%s", args.ArgC() > 1 ? args.Arg(1) : "");
            hlap::Log("refusing: %s", g_refuse[0] ? g_refuse : "(nothing)");
            return PLUGIN_STOP;
        }
        if (std::strcmp(args.Arg(0), "hlap_status") == 0) {
            hlap::Log("frames %u, hook %s, refusing %s, refusals %u", g_frames,
                g_orig_can_have ? "on" : "off", g_refuse[0] ? g_refuse : "(nothing)", g_refusals);
            return PLUGIN_STOP;
        }
        return PLUGIN_CONTINUE;
    }
    PLUGIN_RESULT NetworkIDValidated(const char *, const char *) override { return PLUGIN_CONTINUE; }
    void OnQueryCvarValueFinished(QueryCvarCookie_t, edict_t *, EQueryCvarValueStatus, const char *,
                                  const char *) override {}
    void OnEdictAllocated(edict_t *) override {}
    void OnEdictFreed(const edict_t *) override {}
};

Plugin g_plugin;

}  // namespace

// The engine asks every addons/*.vdf plugin for this by name. tier1's
// EXPOSE_INTERFACE machinery would need tier1.lib; one interface does not.
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) hlap::Log("DllMain attach");
    return TRUE;
}

extern "C" __declspec(dllexport) void *CreateInterface(const char *name, int *rc) {
    hlap::Log("CreateInterface %s", name);
    if (std::strcmp(name, INTERFACEVERSION_ISERVERPLUGINCALLBACKS) == 0) {
        if (rc) *rc = IFACE_OK;
        return &g_plugin;
    }
    if (rc) *rc = IFACE_FAILED;
    return nullptr;
}
