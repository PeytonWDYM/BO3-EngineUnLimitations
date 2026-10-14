"""Replay captured actor entity allocation, destruction, corpse cleanup, and retry."""
from pathlib import Path
import sys,json,hashlib,struct,argparse
from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_OP_IMM,CS_OP_MEM
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--module',type=Path,required=True)
parser.add_argument('--executable',type=Path,required=True)
parser.add_argument('--dependencies',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--production-recipe',action='store_true')
args=parser.parse_args()
OUT=args.output.resolve()
if (Path.home()/'.codex/labs/bo3-engine').resolve() not in OUT.parents or OUT.exists():
 raise ValueError('Use a new result directory inside the private BO3 lab.')
OUT.mkdir(parents=True)
sys.path.insert(0,str(args.dependencies))
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
import unicorn.x86_const as x
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'patches/actor_pool'))
from captured_code import CapturedCode,CodeGuard
C=CapturedCode(args.module,args.executable)
B=C.base
G,A,D,M,S,STOP=B+0x22000000,B+0x23000000,B+0x24000000,B+0x25000000,B+0x26000000,B+0x27000000
STUB=B+0x20000000
REG=lambda name:getattr(x,'UC_X86_REG_'+name)
CS=Cs(CS_ARCH_X86,CS_MODE_64);CS.detail=True
GUARDS=[CodeGuard(0x1b751e0,133,'9394b01b5e5033e8fb232f4586be4bbf521f740966e3334c2a817a7358562b74'),CodeGuard(0x1b75050,283,'c3b0cedbbbed8c29b1b759c1c5e9a58f36a4e80f418442a93ea858aafd0caa67'),CodeGuard(0x1b6b580,949,'13db53bf7cc881a516734f58945d9d30cd7ea5abb5b127f8571f397e219d63c9'),CodeGuard(0x24ef7f0,499,'8921ddf5f7903ee02cabf8b4bf2b6c7236e92ba377651a6d35785b008fc064d3'),CodeGuard(0x24b9d10,1061,'fd52d283dd94dc8213f9ca186baba5ef18897de6c485ed296010e55086b33d0a'),CodeGuard(0x24ae5e0,295,'2bd295d4c09c88bab89bb1d878720a72aa843b4e2fa02bff8cd6d562e5b64fe5'),CodeGuard(0x24ae707,147,'68311ec4af383408fa4f6da9b16483c2a8e6cd7b0c6d43673ae672ab9a4c8220')]
for guard in GUARDS:C.guarded(guard)
# Full native procedures, actual initializer prefix/tail, caller death branch and binding windows.
RANGES=[(g.rva,g.size) for g in GUARDS]+[(0x1b75170,109),(0x1b6d850,6900),(0x24b5eb0,48),(0x24b5ee0,35),(0x24b28c1,0x53),(0x24b64f0,14),(0x24b65e3,11),(0x24b67a1,101)]
RAW={rva:C.read(rva,size) for rva,size in RANGES}
ENDPOINTS=set();INDIRECT=set();DATA_PAGES=set()
for rva,size in RANGES:
 for i in CS.disasm(RAW[rva],B+rva):
  for op in i.operands:
   if op.type==CS_OP_MEM and i.reg_name(op.mem.base)=='rip':DATA_PAGES.add((i.address+i.size+op.mem.disp)&~4095)
  if i.mnemonic=='call':
   if i.operands[0].type==CS_OP_IMM:ENDPOINTS.add(i.operands[0].imm)
   else:INDIRECT.add(i.address)
# Failure cases were written in the private lab before this replay: dedicated full,
# normal full, young reusable head, high-water growth, independent actor/entity IDs,
# DObj cleanup, corpse failure, ring wrap, retry, canaries, and changed-body refusal.
if args.production_recipe:
 from runtime_recipe import prepare_recipe
 recipe=prepare_recipe(C,STUB)
 EDITS=tuple(e for e in recipe.edits if 0x1b751e0<=e.guard.rva<0x1b75265)
else:
 from entity_allocator import prepare_entity_allocator,GUARDS as ALLOCATION_GUARDS,MISS
 EDITS=(prepare_entity_allocator(C,STUB),)
class Machine:
 def __init__(self,high=200,head=None,full_dedicated=True,patched=True):
  self.u=Uc(UC_ARCH_X86,UC_MODE_64);self.pages=set();self.calls={};self.fatal=0;self.corpse_slot=0;self.recycle=None
  for address,span in ((G,2048*0x4f8),(A,500*0x2110),(D,4000)):
   self.map(address-4096,span+8192)
  self.canaries={address:bytes([0xa5])*16 for address in (G-16,G+2048*0x4f8,A-16,A+500*0x2110,D-16,D+4000)}
  for address,value in self.canaries.items():self.u.mem_write(address,value)
  for addr,size in ((G,2048*0x4f8),(A,500*0x2110),(D,4096),(M,0x10000),(S,0x20000),(STOP,4096),(STUB,4096)):self.map(addr,size)
  for rva,size in RANGES:
   self.map(B+rva,size);self.u.mem_write(B+rva,RAW[rva])
  for page in DATA_PAGES:self.map(page,4096)
  for page in (B+0xa1b0000,B+0xa1b6000,B+0xa577000,B+0xa588000,B+0xa589000):self.map(page,4096)
  for target in ENDPOINTS:
   self.map(target,1)
   if not any(B+rva<=target<B+rva+n for rva,n in RANGES):self.u.mem_write(target,b'\xc3')
  for idx in range(24,88):self.put(G+idx*0x4f8+0x1f4,'B',int(full_dedicated))
  for idx in range(184,high):self.put(G+idx*0x4f8+0x1f4,'B',1)
  for idx in range(2048):self.put(G+idx*0x4f8,'I',idx)
  for rva,fmt,val in ((0xa1b0738,'Q',G),(0xa1b0744,'I',high),(0xa1b0748,'Q',G+head*0x4f8 if head is not None else 0),(0xa1b0750,'Q',G+head*0x4f8 if head is not None else 0),(0xa1b0798,'Q',A),(0xa1b6c14,'i',1000000)):
   self.map(B+rva,struct.calcsize(fmt));self.put(B+rva,fmt,val)
  if head is not None:self.put(G+head*0x4f8+0x1f4,'B',0);self.put(G+head*0x4f8+0x2ac,'i',999000)
  if patched:
   for edit in EDITS:
    self.u.mem_write(B+edit.guard.rva,edit.replacement)
    if edit.stub:
     self.map(edit.stub_address,len(edit.stub));self.u.mem_write(edit.stub_address,edit.stub)
  # Already-admitted500 actor destructor operands, applied only to this owned memory.
  self.u.mem_write(B+0x24ae77f,bytes.fromhex('41c74658')+struct.pack('<I',500))
  self.u.mem_write(B+0x24ae750,bytes.fromhex('4881fb')+struct.pack('<I',500*0x2110))
  for site in (0x24ae625,0x24b5ec4):self.u.mem_write(B+site,b'\x48\x8d\x0d'+struct.pack('<i',D-(B+site+7)))
  self.u.hook_add(UC_HOOK_CODE,self.hook)
 def map(self,address,size):
  for page in range(address&~4095,(address+size+4095)&~4095,4096):
   if page not in self.pages:self.u.mem_map(page,4096);self.pages.add(page)
 def put(self,address,fmt,value):self.u.mem_write(address,struct.pack('<'+fmt,value))
 def num(self,address,fmt):return struct.unpack('<'+fmt,self.u.mem_read(address,struct.calcsize(fmt)))[0]
 def rr(self,name):return self.u.reg_read(REG(name))
 def wr(self,name,value):self.u.reg_write(REG(name),value)
 def ret(self,value=0):
  sp=self.rr('RSP');pc=self.num(sp,'Q');self.wr('RAX',value);self.wr('RSP',sp+8);self.wr('RIP',pc)
 def hook(self,uc,address,size,_):
  if address==B+0x1b6d887:
   self.put(self.rr('RBP')+0x10,'Q',G);self.wr('RIP',B+0x1b6f28c);return
  if address in INDIRECT:
   self.calls['authored_indirect_cleanup']=self.calls.get('authored_indirect_cleanup',0)+1;self.wr('RAX',0);self.wr('RIP',address+size);return
  if address==B+0x24ae7a0 and self.recycle is not None:
   self.wr('RIP',STUB+0x100);return
  native=any(B+rva<=address<B+rva+n for rva,n in RANGES)
  if address not in ENDPOINTS or native:return
  rva=address-B;self.calls[hex(rva)]=self.calls.get(hex(rva),0)+1
  if rva==0x2bc53b0:self.u.mem_write(self.rr('RCX'),bytes([self.rr('RDX')&255])*self.rr('R8'));self.ret(self.rr('RCX'))
  elif rva in (0x20ec0b0,0x20ec240):self.fatal+=1;raise AssertionError('Fatal normal-allocation endpoint reached')
  elif rva==0x12d84b0:self.put(self.rr('RCX'),'I',self.rr('RDX')&0xffffffff);self.ret()
  elif rva==0x24c0410:self.ret(self.corpse_slot&0xffffffffffffffff)
  elif rva in (0x20f5ed0,0x22be5e0):self.ret(M)
  elif rva==0x24b6480:
   self.bind_host(self.rr('RCX'),100);self.ret()
  else:self.ret()
 def bind_host(self,entity,index):
  actor=A+index*0x2110;self.put(entity+0x258,'Q',actor);self.put(entity+0x260,'Q',0);self.put(entity+0x1a0,'H',18);self.put(entity+0x58,'I',index)
  self.put(actor,'I',1);self.put(actor+8,'Q',entity);self.put(actor+0x10,'Q',0);self.put(actor+0x78,'I',index);self.put(actor+0x7c,'I',self.num(entity,'I'))
  return actor
 def call(self,rva,args=(),extra=()):
  sp=S+0x1f008;self.u.mem_write(sp,struct.pack('<Q',STOP)+bytes(0x100));self.wr('RSP',sp)
  saved={name:0x66660000+idx for idx,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
  for name,val in saved.items():self.wr(name,val)
  for name,val in zip(('RCX','RDX','R8','R9'),args):self.wr(name,val)
  for idx,val in enumerate(extra):self.put(sp+0x28+8*idx,'Q',val)
  self.u.emu_start(B+rva,STOP,count=1000000)
  assert self.rr('RSP')==sp+8,(hex(rva),'stack',hex(self.rr('RSP')))
  assert all(self.rr(name)==val for name,val in saved.items()),(hex(rva),'nonvolatile')
  return self.rr('RAX')
 def native_bind(self,entity,index):
  actor=A+index*0x2110
  for start,end,seed in ((0x24b64f0,0x24b64fe,{'R14':entity,'RDI':actor,'RAX':0}),(0x24b65e3,0x24b65ee,{'R14':entity,'RDI':actor,'RSI':0}),(0x24b67a1,0x24b6806,{'R14':entity,'RDI':actor,'RBP':0})):
   for name,val in seed.items():self.wr(name,val)
   self.u.emu_start(B+start,B+end,count=1000)
  self.put(actor,'I',1);self.put(entity+0x1a0,'H',18)
  assert self.num(entity+0x258,'Q')==actor and self.num(actor+8,'Q')==entity
  assert self.num(entity+0x58,'I')==index and self.num(actor+0x78,'I')==index and self.num(actor+0x7c,'I')==self.num(entity,'I')
  return actor
 def free_chain(self):
  seen=[];p=self.num(B+0xa1b0748,'Q')
  while p:
   assert p not in seen and G+184*0x4f8<=p<G+1022*0x4f8 and (p-G)%0x4f8==0
   assert self.num(p+0x1f4,'B')==0;seen.append(p);p=self.num(p+0x4b0,'Q')
  assert self.num(B+0xa1b0750,'Q')==(seen[-1] if seen else 0)
  return [(p-G)//0x4f8 for p in seen]
 def enable_recycle(self,entity):
  self.recycle=entity
  stub=b'\x48\x83\xec\x28\x48\xb9'+struct.pack('<Q',entity)+b'\x48\xb8'+struct.pack('<Q',B+0x1b6b580)+b'\xff\xd0\xb8\x01\0\0\0\x48\x83\xc4\x28\xc3'
  self.u.mem_write(STUB+0x100,stub)
CASES=[]
def receipt(name,m,**fields):
 assert all(bytes(m.u.mem_read(address,16))==value for address,value in m.canaries.items()),(name,'allocation canary')
 CASES.append({'allocationCanaries':True,'case':name,'fatalEndpoints':m.fatal,'freeChain':m.free_chain(),**fields})
try:
 for name,high,head,full,young,expected in [('dedicated-free',200,None,False,False,24),('normal-reused-head',200,190,True,False,190),('young-head-grow',200,190,True,True,200),('young-head-at-full',1022,190,True,True,190),('normal-high-water',200,None,True,False,200),('both-full',1022,None,True,False,None)]:
  m=Machine(high,head,full)
  if young:m.put(G+head*0x4f8+0x2ac,'i',999900)
  result=m.call(0x1b751e0)
  assert result==(0 if expected is None else G+expected*0x4f8),(name,hex(result),expected)
  if result:assert m.num(result,'I')==expected and m.num(result+0x1f4,'B')==1
  if expected is None:assert m.calls.get('0x20f0b60')==1 and m.calls.get('0x1b6fa70')==1
  receipt(name,m,entityId=expected,highWater=m.num(B+0xa1b0744,'I'))
 # The unpatched native allocator reports null with the same full dedicated range.
 m=Machine(200,None,True,patched=False);assert m.call(0x1b751e0)==0;receipt('stock-dedicated-full-null',m)
 # Native binding and complete destruction/free with intentionally unrelated IDs.
 for index,entity_id in ((0,190),(64,200),(499,1021)):
  m=Machine(1022,None,True);entity=G+entity_id*0x4f8;actor=m.native_bind(entity,index)
  m.put(D+index*8,'Q',M)
  assert m.call(0x24b5eb0,(actor,))==M
  assert m.call(0x24b5ee0,(actor,))==index
  m.call(0x1b6b580,(entity,))
  assert m.num(actor,'I')==0 and m.num(entity+0x1f4,'B')==0 and m.free_chain()==[entity_id]
  receipt('native-general-actor-free',m,actorIndex=index,entityId=entity_id)
 # Complete native corpse transition followed by its actual caller's free branch.
 for slot in (0,-1):
  m=Machine(1022,None,True);m.corpse_slot=slot;entity=G+200*0x4f8;actor=m.native_bind(entity,499)
  m.put(B+0xa588a68,'Q',M);m.put(B+0xa1c3270,'I',0)
  sp=S+0x1f000;m.wr('RSP',sp);m.wr('RBX',entity);m.wr('RCX',entity)
  try:m.u.emu_start(B+0x24b28c1,B+0x24b2914,count=1000000)
  except Exception:
   print(json.dumps({'rip':hex(m.rr('RIP')-B),'rsp':hex(m.rr('RSP')),'rcx':hex(m.rr('RCX')),'rax':hex(m.rr('RAX')),'calls':m.calls}));raise
  assert m.rr('RSP')==sp and m.num(actor,'I')==0 and m.free_chain()==[200]
  corpse=G+88*0x4f8;assert m.num(corpse+0x1a0,'H')==20
  receipt('native-corpse-then-source-free',m,actorIndex=499,entityId=200,corpseEntityId=88,corpseDObjSlot=slot)
 # Native ring wrapping and occupied-slot destruction remain active.
 m=Machine(200,None,True)
 for idx in range(33):
  result=m.call(0x1b75170);assert result==G+(88+idx%32)*0x4f8
  receipt('native-corpse-ring-33',m,finalEntityId=88)
 # Real script spawn's null -> native free via authored recycle selector -> native retry.
 m=Machine(1022,None,True);old=G+200*0x4f8;m.native_bind(old,499);m.enable_recycle(old)
 result=m.call(0x24ef7f0,(0,M+0x100,M+0x120,0),(1,0,0,0))
 assert result==old and m.num(old+0x1f4,'B')==1 and m.num(A+499*0x2110,'I')==0 and m.free_chain()==[]
 receipt('native-script-recycle-retry',m,entityId=200)
 mrefuse=Machine(1022,None,True)
 assert mrefuse.call(0x24ef7f0,(0,M+0x100,M+0x120,0),(0,0,0,0))==0
 receipt('native-script-full-refusal',mrefuse)
 # Target storage in owned native state: 64 dedicated + 436 normal entities.
 bulk=Machine(184,None,False)
 allocated=[]
 for index in range(500):
  entity=bulk.call(0x1b751e0)
  expected=24+index if index<64 else 184+index-64
  assert entity==G+expected*0x4f8 and entity not in allocated
  allocated.append(entity)
  bulk.native_bind(entity,index)
  bulk.put(D+index*8,'Q',M)
  assert all(bytes(bulk.u.mem_read(address,16))==value for address,value in bulk.canaries.items())
 assert sum(bulk.num(A+index*0x2110,'I')!=0 for index in range(500))==500
 assert bulk.num(B+0xa1b0744,'I')==620
 receipt('owned-500-simultaneous-actor-entities',bulk,dedicated=64,general=436,actorIndices=[0,499],normalEntityIds=[184,619])
 for index,entity in enumerate(allocated[64:],64):
  bulk.call(0x1b6b580,(entity,))
  assert bulk.num(A+index*0x2110,'I')==0 and bulk.num(entity+0x1f4,'B')==0
 assert bulk.free_chain()==list(range(184,620))
 assert sum(bulk.num(A+index*0x2110,'I')!=0 for index in range(500))==64
 receipt('owned-436-normal-actor-release',bulk,released=436,activeActors=64)
 # The freed young head stays queued while stock high-water capacity remains.
 assert bulk.call(0x1b751e0)==G+620*0x4f8 and bulk.free_chain()==list(range(184,620))
 for entity_id in range(621,1022):bulk.put(G+entity_id*0x4f8+0x1f4,'B',1)
 bulk.put(B+0xa1b0744,'I',1022)
 assert bulk.call(0x1b751e0)==G+184*0x4f8 and bulk.free_chain()==list(range(185,620))
 receipt('owned-bulk-young-head-growth-then-full-reuse',bulk,grownEntityId=620,reusedEntityId=184)
 class AlteredCapture:
  guarded=CapturedCode.guarded
  def __init__(self,mutation):self.mutation=mutation;self.base=C.base
  def read(self,rva,size):
   raw=bytearray(C.read(rva,size))
   if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
   return bytes(raw)
 refusals=0
 admission_guards=GUARDS if args.production_recipe else (*ALLOCATION_GUARDS,MISS)
 for guard in admission_guards:
  try:
   if args.production_recipe:AlteredCapture(guard.rva).guarded(guard)
   else:prepare_entity_allocator(AlteredCapture(guard.rva),STUB)
  except ValueError:refusals+=1
  else:raise AssertionError('Changed native body escaped admission')
 artifact=OUT/'final-owned-pools.bin';artifact.write_bytes(bytes(bulk.u.mem_read(G,2048*0x4f8))+bytes(bulk.u.mem_read(A,500*0x2110)))
 report={'passed':True,'productionRecipe':args.production_recipe,'guardRefusals':refusals,'cases':CASES,'guards':[{'rva':hex(g.rva),'size':g.size,'sha256':g.sha256} for g in admission_guards],'identity':{'executableSha256':C.executable_sha256,'manifestSha256':hashlib.sha256(C.manifest.read_bytes()).hexdigest()},'sourceFiles':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path(__file__).resolve().parents[2]/'patches/actor_pool/entity_allocator.py')},'artifact':{'path':str(artifact),'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()},'authoredEndpoints':['protected G_InitGentity pool-pointer decoder binding','native client/server/model/physics/script helper endpoints','actor-record provider for script spawn','oldest-actor recycle selection, which invokes native G_FreeEntity','native corpse DObj record selection'],'scope':'Owned Unicorn native allocation and lifecycle feasibility. Native actor binding windows, full allocators/free/destructor/script-spawn/corpse bodies, and native corpse caller death branch execute. No game writes or complete game/peer/save/migration/Windows-unwind claim.','capacityLimit':'147 free normal slots in captured DE allows at most64+147=211 actors if all other demand stays fixed.300 requires236 normal slots,89 more than observed.500 requires436 normal slots,289 more than observed.'}
 (OUT/'replay-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'cases':len(CASES),'report':str(OUT/'replay-report.json')}))
except Exception as error:
 (OUT/'replay-report.json').write_text(json.dumps({'passed':False,'productionRecipe':args.production_recipe,'cases':CASES,'failure':str(error),'identity':{'executableSha256':C.executable_sha256}},indent=2)+'\n')
 raise
