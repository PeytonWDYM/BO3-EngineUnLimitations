option casemap:none
EXTERN OwnedReaderHome:BYTE, OwnedWriterHome:BYTE, OwnedInsertHome:BYTE, OwnedErrorHome:BYTE
EXTERN NativeClientRead:PROC, NativeClientWrite:PROC, NativeInsert:PROC, NativeError:PROC
PUBLIC OwnedReaderContinuation, OwnedWriterContinuation, OwnedInsertContinuation, OwnedErrorContinuation
.code
OwnedReaderContinuation PROC
    cmp QWORD PTR [rsp+10h],rbx
    sete BYTE PTR [OwnedReaderHome]
    jmp NativeClientRead
OwnedReaderContinuation ENDP
OwnedWriterContinuation PROC
    cmp QWORD PTR [rsp+8h],rbx
    sete BYTE PTR [OwnedWriterHome]
    jmp NativeClientWrite
OwnedWriterContinuation ENDP
; The original static thunk has already pushed RBX before entering this body.
OwnedInsertContinuation PROC FRAME
    .pushreg rbx
    .endprolog
    cmp rbx,r8
    sete BYTE PTR [OwnedInsertHome]
    pop rbx
    jmp NativeInsert
OwnedInsertContinuation ENDP
OwnedErrorContinuation PROC
    cmp QWORD PTR [rsp+20h],r9
    sete BYTE PTR [OwnedErrorHome]
    jmp NativeError
OwnedErrorContinuation ENDP
END
