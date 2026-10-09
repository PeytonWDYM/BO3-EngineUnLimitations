"""Configure the fixed optional 500K checksum startup through Steam Play."""
from pathlib import Path
import sys

SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE.parents[2]/'source'))
from launch.late_startup.SteamSetup import FixedSteamRecipe,LateSteam,PatchError,SteamPlay,main as shared_main,recipe as shared_recipe

FILES=('BO3-500K-Zombies.exe','Bo3EnhancedHelper.dll','Bo3StartupGate.dll','Detours-LICENSE.md')
CONTROLLERS=(FILES[0],'BO3-Integrity-Zombies.exe','BO3-Job-Zombies.exe','BO3-Late-Passive-Control.exe',
    'BO3-Late-Control.exe','BO3-Startup-Control.exe','BO3-Late-Zombies.exe','BO3-Enhanced-Zombies.exe')
RECIPE_PATH=SOURCE/'SteamProfile.json'
RECIPE_SHA256='dc849b0e3ebb11c691dd6ea1e4e4519141a3f2f922bd861e922b9c0c328a0283'


def fixed_recipe() -> FixedSteamRecipe:
    return FixedSteamRecipe(RECIPE_PATH,RECIPE_SHA256,FILES,'500k-zombies','earlyChecksumRecipeSha256',
        'EXPERIMENTAL: 500,000 intended server script slots. Game startup, AAE loading and friends require manual validation.')


def recipe() -> dict:
    return shared_recipe(fixed_recipe())


class EarlySteam(LateSteam):
    def __init__(self,manager: SteamPlay,*,tools_root: Path | None=None):
        super().__init__(manager,tools_root=tools_root,fixed=fixed_recipe())
        provider=manager.process_running
        manager.process_running=lambda name:provider(name) or any(provider(controller) for controller in CONTROLLERS)


if __name__=='__main__':
    try:raise SystemExit(shared_main(EarlySteam,__doc__))
    except (PatchError,OSError,ValueError) as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
