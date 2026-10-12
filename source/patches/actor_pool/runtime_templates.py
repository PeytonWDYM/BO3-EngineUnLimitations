"""Represent runtime relocation without storing complete native function bodies."""
from dataclasses import dataclass
import struct
import capstone
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

@dataclass(frozen=True)
class Address:
    space: str
    offset: int

@dataclass(frozen=True)
class Piece:
    offset: int
    size: int
    source: int | None
    data: bytes = b''

@dataclass(frozen=True)
class Relocation:
    offset: int
    width: int
    target: Address
    next_offset: int | None

@dataclass(frozen=True)
class Template:
    origin: Address
    size: int
    pieces: tuple[Piece,...]
    relocations: tuple[Relocation,...]

def make_template(code,recipe,space: str,offset: int,body: bytes,instruction_map=()) -> Template:
    if space not in ('game','arena') or not body:raise ValueError('The runtime template origin or extent is invalid.')
    pieces=[]
    if instruction_map:
        rows=sorted(instruction_map)
        for (source,destination),(next_source,next_destination) in zip(rows,rows[1:]):
            start=destination-(recipe.arena+offset);size=next_destination-destination
            native=code.read(source-code.base,next_source-source);changed=body[start:start+size]
            if len(changed)!=size or start<0:raise ValueError('A relocated instruction span exceeds its body.')
            if len(native)!=size:
                pieces.append(Piece(start,size,None,changed));continue
            pieces.append(Piece(start,size,source-code.base))
            position=0
            while position<size:
                if native[position]==changed[position]:position+=1;continue
                end=position+1
                while end<size and native[end]!=changed[end]:end+=1
                pieces.append(Piece(start+position,end-position,None,changed[position:end]));position=end
    else:pieces.append(Piece(0,len(body),None,body))
    relocations=[]
    address=(code.base if space=='game' else recipe.arena)+offset
    def target(value: int) -> Address:
        if code.base<=value<code.base+code.meta['imageSize']:return Address('game',value-code.base)
        if recipe.arena<=value<recipe.arena+recipe.arena_bytes:return Address('arena',value-recipe.arena)
        raise ValueError('A runtime code operand targets an unadmitted address interval.')
    # Native data edits contain RVA/count/cookie words, not executable operands.
    if space=='arena' or offset<0x2F00000:
        decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
        instructions=list(decoder.disasm(body,address))
        if sum(i.size for i in instructions)!=len(body):raise ValueError('The runtime body does not decode completely.')
        for instruction in instructions:
            start=instruction.address-address
            if instruction.group(capstone.CS_GRP_BRANCH_RELATIVE):
                operand=instruction.operands[0]
                if operand.type!=X86_OP_IMM or instruction.imm_size not in (1,4):
                    raise ValueError('The runtime branch has an unknown displacement encoding.')
                relocations.append(Relocation(start+instruction.imm_offset,instruction.imm_size,target(operand.imm),start+instruction.size))
            for operand in instruction.operands:
                if operand.type==X86_OP_MEM and operand.mem.base==X86_REG_RIP:
                    if instruction.disp_size!=4:raise ValueError('The runtime RIP operand has an unknown displacement width.')
                    relocations.append(Relocation(start+instruction.disp_offset,4,target(instruction.address+instruction.size+operand.mem.disp),start+instruction.size))
                elif operand.type==X86_OP_IMM and instruction.imm_size==8:
                    value=operand.imm&((1<<64)-1)
                    if code.base<=value<code.base+code.meta['imageSize'] or recipe.arena<=value<recipe.arena+recipe.arena_bytes:
                        relocations.append(Relocation(start+instruction.imm_offset,8,target(value),None))
    return Template(Address(space,offset),len(body),tuple(pieces),tuple(relocations))

def render_template(template: Template,code,game: int,arena: int) -> bytes:
    bases={'game':game,'arena':arena};body=bytearray(template.size);covered=bytearray(template.size)
    for piece in template.pieces:
        raw=code.read(piece.source,piece.size) if piece.source is not None else piece.data
        if len(raw)!=piece.size or not 0<=piece.offset<=template.size-piece.size:
            raise ValueError('A runtime copy/literal span exceeds its complete body.')
        body[piece.offset:piece.offset+piece.size]=raw;covered[piece.offset:piece.offset+piece.size]=b'\1'*piece.size
    if not all(covered):raise ValueError('A runtime body has an uninitialized instruction span.')
    origin=bases[template.origin.space]+template.origin.offset
    for field in template.relocations:
        value=bases[field.target.space]+field.target.offset
        if field.next_offset is not None:value-=origin+field.next_offset
        if field.width not in (1,4,8) or not 0<=field.offset<=len(body)-field.width:
            raise ValueError('A runtime relocation exceeds its complete operand.')
        body[field.offset:field.offset+field.width]=value.to_bytes(field.width,'little',signed=field.next_offset is not None)
    return bytes(body)
