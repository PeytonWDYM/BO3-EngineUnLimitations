#pragma once
#include "Common.h"
#include <filesystem>

namespace patch {
struct Record {
    uint64_t rva;
    std::vector<uint8_t> original;
    std::vector<uint8_t> replacement;
};

struct Profile {
    std::string id;
    std::filesystem::path target;
    std::string sha256;
    uint32_t image_size;
    uint32_t timestamp;
    std::string safety;
    std::vector<Record> records;
};

Profile load_profile(const std::filesystem::path& path);
uint64_t parse_number(const std::string& text);
}
