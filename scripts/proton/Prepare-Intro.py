#!/usr/bin/env python3
"""Prepare a local startup clip for the admitted BO3 engine movie parser and PCM sound helper."""
import argparse
from pathlib import Path
import subprocess
import tempfile

masters={0x1a45dfa3,0x18538067,0x1549a966,0x1654ae6b,0xae,0xe0,0xe1,0x1f43b675}
remove={0x114d9b74,0x1254c367,0x1c53bb6b,0xec,0xbf}
def vint(b,p,isid=False):
 first=b[p];n=9-first.bit_length()
 if not 1<=n<=8 or p+n>len(b):raise ValueError('Invalid EBML integer')
 v=int.from_bytes(b[p:p+n],'big');return (v if isid else v&((1<<(7*n))-1)),n

def elem(i,payload):
 key=i.to_bytes((i.bit_length()+7)//8,'big')
 # BO3 uses signed VINT decoding even for element sizes. Keep size positive.
 return key+(len(payload)|(1<<56)).to_bytes(8,'big')+payload

def avcc(b):
 if len(b)<8 or b[0]!=1:raise ValueError('Invalid AVC configuration')
 p=6
 for _ in range(b[5]&31):n=int.from_bytes(b[p:p+2],'big');p+=2+n
 npps=b[p];p+=1
 for _ in range(npps):n=int.from_bytes(b[p:p+2],'big');p+=2+n
 if p>len(b) or (b[5]&31)!=1 or npps!=1:raise ValueError('BO3 requires one SPS/PPS pair')
 # BO3 reads just the first SPS/PPS and resumes the EBML loop at that point.
 return b[:p]

def repack(b):
 result=[];p=0
 while p<len(b):
  i,ni=vint(b,p,True);n,nn=vint(b,p+ni);start=p+ni+nn;end=start+n
  if end>len(b):raise ValueError(f'EBML span exceeds container {i:x}')
  payload=b[start:end];p=end
  if i in remove:continue
  if i in masters:
   payload=repack(payload)
   if i==0x18538067:payload+=elem(0x1c53bb6b,b'') # Native parser uses Cues as end marker.
  elif i==0x63a2:payload=avcc(payload)
  result.append(elem(i,payload))
 return b''.join(result)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path,help='Local clip with a video and audio stream')
    parser.add_argument('output',type=Path,help='New directory outside the repository')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[2]
    output=args.output.resolve()
    if output.is_relative_to(repo) or output.exists():
        raise SystemExit('Use a new output directory outside the repository.')
    source=args.input.resolve(strict=True)
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        intermediate=Path(temporary)/'encoded.mkv'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(source),'-map','0:v:0',
            '-vf','scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1',
            '-r','30000/1001','-c:v','libx264','-profile:v','high','-level:v','4.0','-pix_fmt','yuv420p',
            '-an',str(intermediate)],check=True)
        audio=Path(temporary)/'audio.wav'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(source),'-map','0:a:0','-vn',
            '-ar','48000','-ac','2','-c:a','pcm_s16le',str(audio)],check=True)
        movie=repack(intermediate.read_bytes())
        if not movie or audio.stat().st_size<=44:
            raise SystemExit('The custom intro video or audio is empty.')
        (output/'BO3_500K_Custom_Intro.mkv').write_bytes(movie)
        audio.replace(output/'BO3_500K_Custom_Intro.wav')
    print('Prepared engine movie and stereo PCM audio:',output)

if __name__=='__main__':
    main()
