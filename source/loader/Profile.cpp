#include "Profile.h"
#include <algorithm>
#include <charconv>
#include <cctype>
#include <fstream>
#include <limits>
#include <set>
#include <sstream>

namespace patch {
uint64_t parse_number(const std::string& text) {
    uint64_t result = 0;
    const bool hex = text.starts_with("0x");
    const char* start = text.data() + (hex ? 2 : 0);
    const auto parsed = std::from_chars(start, text.data() + text.size(), result, hex ? 16 : 10);
    if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size() || start == parsed.ptr) throw std::runtime_error("Invalid unsigned number.");
    return result;
}

static std::vector<uint8_t> parse_hex(const std::string& text) {
    if (text.empty() || text.size() % 2 || text.size() > 8192) throw std::runtime_error("Invalid hex byte length.");
    std::vector<uint8_t> bytes;
    bytes.reserve(text.size() / 2);
    for (size_t offset = 0; offset < text.size(); offset += 2) {
        unsigned int value = 0;
        const auto parsed = std::from_chars(text.data() + offset, text.data() + offset + 2, value, 16);
        if (parsed.ec != std::errc{} || parsed.ptr != text.data() + offset + 2) throw std::runtime_error("Invalid hex bytes.");
        bytes.push_back(static_cast<uint8_t>(value));
    }
    return bytes;
}

Profile load_profile(const std::filesystem::path& path) {
    if (std::filesystem::file_size(path) > 1024 * 1024) throw std::runtime_error("Profile exceeds 1 MiB.");
    std::ifstream file(path);
    std::string line;
    std::getline(file, line);
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line != "BO3_RUNTIME_PATCH_PROFILE 1") throw std::runtime_error("Unsupported profile header.");
    Profile result{};
    std::set<std::string> fields;
    size_t total = 0;
    while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line.starts_with('#')) continue;
        const auto separator = line.find(' ');
        if (separator == std::string::npos || separator + 1 == line.size()) throw std::runtime_error("Missing profile field value.");
        const auto key = line.substr(0, separator);
        const auto value = line.substr(separator + 1);
        if (key == "patch") {
            std::istringstream tokens(value);
            std::string rva, original, replacement, extra;
            if (!(tokens >> rva >> original >> replacement) || tokens >> extra) throw std::runtime_error("Invalid patch record.");
            Record record{parse_number(rva), parse_hex(original), parse_hex(replacement)};
            if (record.original.size() != record.replacement.size()) throw std::runtime_error("Patch byte length differs.");
            if (record.original == record.replacement) throw std::runtime_error("Patch does not change bytes.");
            if (record.rva >= result.image_size || record.original.size() > result.image_size - record.rva) throw std::runtime_error("Patch exceeds image bounds.");
            total += record.original.size();
            if (result.records.size() >= 128 || total > 65536) throw std::runtime_error("Profile exceeds patch record limits.");
            result.records.push_back(std::move(record));
            continue;
        }
        if (!fields.insert(key).second) throw std::runtime_error("Profile has a duplicate field: " + key);
        if (key == "id") result.id = value;
        else if (key == "target") {
            result.target = std::filesystem::path(widen(value));
            if (!result.target.is_absolute()) throw std::runtime_error("Target path must be absolute.");
        } else if (key == "sha256") {
            if (parse_hex(value).size() != 32) throw std::runtime_error("SHA256 must contain 32 bytes.");
            result.sha256 = value;
            std::transform(result.sha256.begin(), result.sha256.end(), result.sha256.begin(), [](char c) { return static_cast<char>(std::tolower(static_cast<unsigned char>(c))); });
        } else if (key == "image_size" || key == "timestamp") {
            const auto number = parse_number(value);
            if (number > std::numeric_limits<uint32_t>::max()) throw std::runtime_error("PE field exceeds 32 bits.");
            if (key == "image_size") result.image_size = static_cast<uint32_t>(number);
            else result.timestamp = static_cast<uint32_t>(number);
        } else if (key == "safety") result.safety = value;
        else throw std::runtime_error("Unknown profile field: " + key);
    }
    const std::set<std::string> required{"id", "target", "sha256", "image_size", "timestamp", "safety"};
    if (fields != required || result.records.empty()) throw std::runtime_error("Profile is missing required fields or records.");
    // Keep profile order so rollback tests can exercise a later failure.
    for (size_t i = 0; i < result.records.size(); ++i) {
        const auto& a = result.records[i];
        for (size_t j = 0; j < i; ++j) {
            const auto& b = result.records[j];
            if (a.rva < b.rva + b.original.size() && b.rva < a.rva + a.original.size()) throw std::runtime_error("Patch records overlap.");
        }
    }
    return result;
}
}
