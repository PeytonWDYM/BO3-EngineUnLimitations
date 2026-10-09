option casemap:none
EXTERN Bo3IntroAudioBindings:BYTE
.code
NativeOriginalIntro PROC FRAME
    mov rax,rsp
    push rbp
    .pushreg rbp
    push rsi
    .pushreg rsi
    .endprolog
    jmp QWORD PTR [Bo3IntroAudioBindings+40]
NativeOriginalIntro ENDP
NativeOriginalIntroUpdate PROC FRAME
    push rdi
    .pushreg rdi
    sub rsp,20h
    .allocstack 20h
    .endprolog
    jmp QWORD PTR [Bo3IntroAudioBindings+48]
NativeOriginalIntroUpdate ENDP
END
