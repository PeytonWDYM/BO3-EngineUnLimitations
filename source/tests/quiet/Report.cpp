#include "Fixture.h"
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace fixture {
void Require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
void Ok(HRESULT result) { if (FAILED(result)) throw std::runtime_error("Unexpected HRESULT " + Hresult(result)); }
std::string Hresult(HRESULT result) {
    std::ostringstream text;
    text << "0x" << std::hex << std::setw(8) << std::setfill('0') << static_cast<unsigned long>(result);
    return text.str();
}
std::string Hex(const std::vector<BYTE>& bytes) {
    std::ostringstream text;
    for (size_t index = 0; index < (std::min)(bytes.size(), size_t{16}); ++index)
        text << std::hex << std::setw(2) << std::setfill('0') << static_cast<unsigned>(bytes[index]);
    return text.str();
}
std::string Quote(const std::string& value) {
    std::string output = "\"";
    for (char character : value) {
        if (character == '\\' || character == '"') output += '\\';
        output += character;
    }
    return output + '"';
}
void Scenario::Number(const std::string& key, unsigned value) { evidence.emplace_back(key, std::to_string(value)); }
void Scenario::String(const std::string& key, const std::string& value) { evidence.emplace_back(key, Quote(value)); }
void Scenario::Boolean(const std::string& key, bool value) { evidence.emplace_back(key, value ? "true" : "false"); }
int Report::Write(const char* path, bool baseline) const {
    std::ofstream output(path, std::ios::binary);
    if (!output) return 2;
    const auto failures = std::count_if(scenarios.begin(), scenarios.end(), [](const Scenario& test) { return !test.passed; });
    output << "{\n  \"schema\": 1,\n  \"scope\": \"SDK interfaces to owned memory sinks only; no physical audio device or BO3 launch\",\n";
    output << "  \"mode\": " << Quote(baseline ? "unprotected-baseline" : "protected") << ",\n";
    output << "  \"expectedFailure\": " << (baseline ? "true" : "false") << ",\n";
    output << "  \"passed\": " << scenarios.size() - failures << ",\n  \"failed\": " << failures << ",\n  \"scenarios\": [\n";
    for (size_t index = 0; index < scenarios.size(); ++index) {
        const auto& test = scenarios[index];
        output << "    {\"name\": " << Quote(test.name) << ", \"passed\": " << (test.passed ? "true" : "false") << ", \"error\": " << Quote(test.error) << ", \"evidence\": {";
        for (size_t item = 0; item < test.evidence.size(); ++item) {
            if (item) output << ", ";
            output << Quote(test.evidence[item].first) << ": " << test.evidence[item].second;
        }
        output << "}}" << (index + 1 < scenarios.size() ? "," : "") << '\n';
    }
    output << "  ]\n}\n";
    return failures ? 1 : 0;
}
}
