// Console output that also lands in addons/hlap_log.txt, flushed per line, so
// a crash still leaves a record of how far the plugin got.
#pragma once

namespace hlap {
void Log(const char *fmt, ...);
}
