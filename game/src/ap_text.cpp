#include "ap_text.h"

#include <cstdlib>

namespace ap {

std::vector<std::string> Split(const std::string& text, char delimiter) {
    std::vector<std::string> parts;
    std::string current;
    for (char c : text) {
        if (c == delimiter) {
            parts.push_back(current);
            current.clear();
        } else {
            current.push_back(c);
        }
    }
    parts.push_back(current);
    return parts;
}

static bool IsSpace(char c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\v' || c == '\f';
}

std::string Trim(const std::string& text) {
    size_t start = 0;
    size_t end = text.size();
    while (start < end && IsSpace(text[start])) {
        ++start;
    }
    while (end > start && IsSpace(text[end - 1])) {
        --end;
    }
    return text.substr(start, end - start);
}

bool StartsWith(const std::string& text, const std::string& prefix) {
    return text.size() >= prefix.size() &&
           text.compare(0, prefix.size(), prefix) == 0;
}

std::string Lower(const std::string& text) {
    std::string out = text;
    for (char& c : out) {
        if (c >= 'A' && c <= 'Z') {
            c = static_cast<char>(c - 'A' + 'a');
        }
    }
    return out;
}

bool ParseBool(const std::string& text) {
    return Trim(text) == "1";
}

long ParseLong(const std::string& text, long fallback) {
    const std::string trimmed = Trim(text);
    if (trimmed.empty()) {
        return fallback;
    }
    char* end = nullptr;
    const long value = std::strtol(trimmed.c_str(), &end, 10);
    if (end == trimmed.c_str()) {
        return fallback;
    }
    return value;
}

bool ParseVector(const std::string& text, float out[3]) {
    const char* cursor = text.c_str();
    for (int i = 0; i < 3; ++i) {
        char* end = nullptr;
        const float value = std::strtof(cursor, &end);
        if (end == cursor) {
            return false;
        }
        out[i] = value;
        cursor = end;
    }
    return true;
}

std::string Sanitise(const std::string& text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        if (c == '|') {
            out.push_back('/');
        } else if (c == '\r' || c == '\n') {
            out.push_back(' ');
        } else {
            out.push_back(c);
        }
    }
    return out;
}

}  // namespace ap
