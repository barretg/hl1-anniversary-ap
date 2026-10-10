#include "hud.h"
#include "cl_util.h"

#include "ap_hdlock.h"

#include <cstring>

namespace {

// The engine's cmd_function_t. A command handle from GetFirstCmdFunctionHandle
// is a pointer to one.
struct EngineCommand
{
	EngineCommand *next;
	const char *name;
	void ( *function )( void );
	int flags;
};

const char *const kCommand = "_sethdmodels";

void ( *g_pfnOriginal )( void ) = NULL;

void SetHDModels( void )
{
	cvar_t *locked = gEngfuncs.pfnGetCvarPointer( "ap_hd_locked" );
	if ( locked && locked->value != 0.0f )
	{
		// The console once, and the chat area marked as already in it.
		const char *const message = "[AP] HD models cannot be switched on this map: it is "
			"at the precache limit. Switch after the next map loads.\n";
		gEngfuncs.Con_Printf( "%s", message );
		gHUD.m_SayText.SayTextPrint( message, static_cast<int>( strlen( message ) ) + 1, -1,
			true );
		return;
	}
	if ( g_pfnOriginal )
		g_pfnOriginal();
}

} // namespace

void APHDLock_VidInit()
{
	if ( g_pfnOriginal )
		return;
	for ( unsigned int handle = gEngfuncs.GetFirstCmdFunctionHandle(); handle;
		handle = gEngfuncs.GetNextCmdFunctionHandle( handle ) )
	{
		const char *name = gEngfuncs.GetCmdFunctionName( handle );
		if ( !name || stricmp( name, kCommand ) )
			continue;
		EngineCommand *command = reinterpret_cast<EngineCommand *>( handle );
		// Our own handler already: a client dll reloaded in the same process.
		if ( command->function == SetHDModels )
			return;
		g_pfnOriginal = command->function;
		command->function = SetHDModels;
		gEngfuncs.Con_Printf( "[AP] %s hooked\n", kCommand );
		return;
	}
	gEngfuncs.Con_Printf( "[AP] %s not found; the HD option is not locked\n", kCommand );
}
