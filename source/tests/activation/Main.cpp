#include "Harness.h"
#include <iostream>
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    fixture::Report report;
    activation_test::WasapiScenarios(report);
    activation_test::OtherScenarios(report);
#ifdef ACTIVATION_BASELINE
    constexpr bool baseline = true;
#else
    constexpr bool baseline = false;
#endif
    const int result = report.Write(argv[1], baseline);
    std::cout << "Memory-provider activation fixture result " << result << ": " << argv[1] << '\n';
    return result;
}
