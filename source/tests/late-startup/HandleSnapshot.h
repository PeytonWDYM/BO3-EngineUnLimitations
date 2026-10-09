#pragma once
#include <Windows.h>
#include <filesystem>
#include <string>
#include <vector>
// Capture only this owned runner's handles through the documented process snapshot API.
std::vector<std::string> SaveHandles(const std::filesystem::path& path);
