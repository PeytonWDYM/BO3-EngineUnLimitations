#pragma once
#include "NativeContract.h"
void SetupNativeImage(NativeShared*);
void RunNativeExports();
extern "C" unsigned char OwnedReaderHome,OwnedWriterHome,OwnedInsertHome,OwnedErrorHome;
extern "C" void OwnedReaderContinuation(),OwnedWriterContinuation(),OwnedInsertContinuation(),OwnedErrorContinuation();
