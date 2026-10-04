// The Source SDK 2013 headers this plugin uses, with the one fix clang needs.
#pragma once

#include "tier0/platform.h"

// bitbuf.h puts RESTRICT (__restrict) on a member function's definition but not
// its declaration. MSVC accepts the mismatch; clang calls it a conflicting
// redeclaration. The qualifier is an optimisation hint, so drop it.
#undef RESTRICT
#define RESTRICT

#include "eiface.h"
#include "engine/iserverplugin.h"
#include "tier0/dbg.h"
#include "tier1/convar.h"
