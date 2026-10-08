"""Configure one fixed experimental stock job-control recipe through Steam Play."""
from pathlib import Path
import sys

SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE.parents[2]/'source'))
from launch.late_startup.SteamSetup import FixedSteamRecipe,LateSteam,PatchError,SteamPlay,main as shared_main,recipe as shared_recipe

FILES=('BO3-Job-Control.exe','Bo3EnhancedHelper.dll','Bo3StartupGate.dll','Detours-LICENSE.md')
CONTROLLERS=(FILES[0],'BO3-Job-Zombies.exe','BO3-Late-Passive-Control.exe','BO3-Late-Control.exe','BO3-Startup-Control.exe','BO3-Late-Zombies.exe','BO3-Enhanced-Zombies.exe')
RECIPE_PATH=SOURCE/'SteamProfile.json'
RECIPE_SHA256='d440224113b0907dab699c5bbbbdd75a60e82cdd5cf9260e16ea5c48d137d87a'


def fixed_recipe() -> FixedSteamRecipe:
    return FixedSteamRecipe(RECIPE_PATH,RECIPE_SHA256,FILES,'job-control','jobControlRecipeSha256',
        'EXPERIMENTAL: exact-host stock capacity (129,999 usable server slots), zero native edits and no expanded-pool enrollment. Game loading, AAE and friends remain unvalidated.')


def recipe() -> dict:
    return shared_recipe(fixed_recipe())


class ControlSteam(LateSteam):
    # Use this wrapper for all control setup/removal. tools_root supports owned fixtures only.
    def __init__(self,manager: SteamPlay,*,tools_root: Path | None=None):
        super().__init__(manager,tools_root=tools_root,fixed=fixed_recipe())
        provider=manager.process_running
        manager.process_running=lambda name:provider(name) or any(provider(controller) for controller in CONTROLLERS)


if __name__=='__main__':
    try:raise SystemExit(shared_main(ControlSteam,__doc__))
    except (PatchError,OSError,ValueError) as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
