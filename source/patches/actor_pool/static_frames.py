"""Emit the called reset template with static PE unwind data. Live actor binding remains gated."""
import re


def emit_called_frame(name: str,body: bytes,metadata: bytes) -> str:
    """The current loader experiment accepts only the independent 40-byte reset frame."""
    if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name) is None:
        raise ValueError('Use a plain MASM symbol for the static frame template.')
    instructions=((0,'4883ec28'),(4,'e8'),(9,'48b9'),(19,'33d241b8'),(27,'e8'),(32,'48b8'),(42,'4883c428c3'))
    if (metadata!=bytes.fromhex('0104010004420000') or len(body)!=47
            or any(body[offset:offset+len(bytes.fromhex(value))]!=bytes.fromhex(value) for offset,value in instructions)):
        raise ValueError('The static experiment requires the complete called reset frame.')
    def row(raw: bytes) -> str:return 'DB '+','.join(f'0{value:02X}h' for value in raw)
    return '\n'.join([
        'option casemap:none','option dotname',f'PUBLIC {name}','PUBLIC Bo3OwnedMemsetRelay','PUBLIC Bo3OwnedClearTarget',
        '.data','ALIGN 8','Bo3OwnedClearTarget DQ 0',
        '.code','ALIGN 16',f'{name} LABEL BYTE',row(body),f'{name}End LABEL BYTE',
        'ALIGN 16','Bo3OwnedMemsetRelay LABEL BYTE','jmp QWORD PTR [Bo3OwnedClearTarget]',
        '.xdata SEGMENT READONLY','ALIGN 4',f'{name}Unwind LABEL BYTE',row(metadata),'.xdata ENDS',
        '.pdata SEGMENT READONLY','ALIGN 4',f'DD IMAGEREL {name},IMAGEREL {name}End,IMAGEREL {name}Unwind',
        '.pdata ENDS','END',''])
