// Small string helpers shared by the parsers.
//
// Deliberately dependency-free: `ap_checkdata`, `ap_bridge` and `ap_state` are
// the part of the game side that can be built and tested without the engine, and
// nothing here reaches for the SDK.

#pragma once

#include <string>
#include <vector>

namespace ap {

// Split on one delimiter. Empty fields are kept, because a record's field count
// is how it is recognised and dropping an empty one would shift the rest.
std::vector<std::string> Split(const std::string& text, char delimiter);

// Trim ASCII whitespace, including the \r a file written on Windows and read on
// Linux carries at the end of every line.
std::string Trim(const std::string& text);

bool StartsWith(const std::string& text, const std::string& prefix);

// ASCII lowercase, for matching a mission by name.
std::string Lower(const std::string& text);

// "1" and "0" as the generators write them. Anything else is false.
bool ParseBool(const std::string& text);

long ParseLong(const std::string& text, long fallback = 0);

// "x y z" -> three floats. False when the field is not three numbers, which is
// how an absent optional position is told from a malformed one.
bool ParseVector(const std::string& text, float out[3]);

// Everything the protocol forbids inside a field: the delimiter and newlines.
// Applied to player names and chat text, which are the only values in the
// protocol a person can choose.
std::string Sanitise(const std::string& text);

}  // namespace ap
