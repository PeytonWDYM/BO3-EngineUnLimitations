"""Configure one fixed passive stock-capacity startup diagnostic through Steam Play."""
from pathlib import Path
import sys

SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE))
from SteamSetup import FixedSteamRecipe,LateSteam,PatchError,SteamPlay,main as shared_main,recipe as shared_recipe

FILES=('BO3-Late-Passive-Control.exe','Bo3EnhancedHelper.dll','Bo3StartupGate.dll','Detours-LICENSE.md')
RECIPE_PATH=SOURCE/'SteamPassiveControlProfile.json'
# Bind the final native build and native-only review before deployment.
RECIPE_SHA256='32e6bf16ecb10863bdd62eaa3015f40d8fe906d3454376adef3bd62e500d463c'


def fixed_recipe() -> FixedSteamRecipe:
    return FixedSteamRecipe(RECIPE_PATH,RECIPE_SHA256,FILES,'late-startup-passive-control','latePassiveControlRecipeSha256',
        'DIAGNOSTIC: stock 129,999 server script slots. No debugger attaches. The owned game closes after 120 seconds. No expanded pool or codec activates.')


def recipe() -> dict:
    return shared_recipe(fixed_recipe())


class PassiveLateSteam(LateSteam):
    # The CLI admits one passive recipe. tools_root supports owned fixtures only.
    # Use this wrapper for passive setup and removal. It also checks the passive parent before its child exists.
    def __init__(self,manager: SteamPlay,*,tools_root: Path | None=None):
        super().__init__(manager,tools_root=tools_root,fixed=fixed_recipe())
        provider=manager.process_running
        manager.process_running=lambda name:provider(name) or provider(FILES[0])


if __name__=='__main__':
    try:raise SystemExit(shared_main(PassiveLateSteam,__doc__))
    except (PatchError,OSError,ValueError) as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
