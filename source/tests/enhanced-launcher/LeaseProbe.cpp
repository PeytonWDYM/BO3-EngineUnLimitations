#include "../../launch/enhanced/LaunchLease.h"
#include <iostream>

int main(int argc, char**) {
    try {
        bo3::enhanced::LaunchLease lease;
        std::cout << "lease acquired\n" << std::flush;
        if (argc == 2) Sleep(15000);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
