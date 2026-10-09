#pragma once
#include "../../tests/startup/Consumers.h"
#include "../activation/ActivationBoundary.h"

extern ComFactory OriginalCom;
extern SoundFactory OriginalSound;
activation::Boundary& OwnedBoundary();
bool DestroyOwnedRuntime();
bool RemoveOwnedHooks();
