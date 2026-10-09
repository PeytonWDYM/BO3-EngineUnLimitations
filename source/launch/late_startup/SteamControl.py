"""Configure one fixed stock-capacity late-startup diagnostic through Steam Play."""
from pathlib import Path
import sys

SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE))
from SteamSetup import FixedSteamRecipe,LateSteam,PatchError,SteamPlay,main as shared_main,recipe as shared_recipe

FILES=('BO3-Late-Control.exe','Bo3EnhancedHelper.dll','Bo3StartupGate.dll','Detours-LICENSE.md')
RECIPE_PATH=SOURCE/'SteamControlProfile.json'
# Bind the final owned native build and independent review before deployment.
RECIPE_SHA256='50fbacf4455e00d9a2b25fb6b424fa6338392c00a0aa52be0031eea219cab0d6'


def fixed_recipe() -> FixedSteamRecipe:
    return FixedSteamRecipe(RECIPE_PATH,RECIPE_SHA256,FILES,'late-startup-control','lateControlRecipeSha256',
        'DIAGNOSTIC: stock 129,999 server script slots. The owned game closes after 120 seconds. No expanded pool or codec activates.')


def recipe() -> dict:
    return shared_recipe(fixed_recipe())


class StockLateSteam(LateSteam):
    # The public CLI selects this fixed diagnostic. tools_root supports owned fixtures only.
    def __init__(self,manager: SteamPlay,*,tools_root: Path | None=None):
        super().__init__(manager,tools_root=tools_root,fixed=fixed_recipe())


if __name__=='__main__':
    try:raise SystemExit(shared_main(StockLateSteam,__doc__))
    except (PatchError,OSError,ValueError) as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
