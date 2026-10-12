option casemap:none
EXTERN Bo3ActorReadBranches:QWORD
PUBLIC ActorReadReentry
PUBLIC SentientReadReentry
PUBLIC SecondaryReadReentry
PUBLIC ActorLoadReentry
.code
; Replay the exact five-byte native entry before its unchanged continuation.
ActorReadReentry PROC
    mov [rsp+8], rbx
    jmp QWORD PTR [Bo3ActorReadBranches]
ActorReadReentry ENDP
SentientReadReentry PROC
    mov [rsp+8], rbx
    jmp QWORD PTR [Bo3ActorReadBranches+8]
SentientReadReentry ENDP
SecondaryReadReentry PROC
    mov [rsp+8], rbx
    jmp QWORD PTR [Bo3ActorReadBranches+16]
SecondaryReadReentry ENDP
ActorLoadReentry PROC FRAME
    sub rsp, 28h
    .allocstack 28h
    .endprolog
    test rcx, rcx
    ; Keep TEST flags and avoid a false epilogue while the native frame remains active.
    mov r11, QWORD PTR [Bo3ActorReadBranches+24]
    jmp r11
ActorLoadReentry ENDP
END
