"""Configure one fixed experimental job-startup Zombies recipe through Steam Play."""
from pathlib import Path
import sys

SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE.parents[2]/'source'))
from launch.late_startup.SteamSetup import FixedSteamRecipe,LateSteam,PatchError,SteamPlay,main as shared_main,recipe as shared_recipe

FILES=('BO3-Job-Zombies.exe','Bo3EnhancedHelper.dll','Bo3StartupGate.dll','Detours-LICENSE.md')
CONTROLLERS=(FILES[0],'BO3-Late-Passive-Control.exe','BO3-Late-Control.exe','BO3-Startup-Control.exe','BO3-Late-Zombies.exe','BO3-Enhanced-Zombies.exe')
RECIPE_PATH=SOURCE/'SteamProfile.json'
# Freeze the final native build and native-only review before deployment.
RECIPE_SHA256='bce1c46455b37c7c94cba6136285685a09af7221b832162d61a1c715a9b08d71'


def fixed_recipe() -> FixedSteamRecipe:
    return FixedSteamRecipe(RECIPE_PATH,RECIPE_SHA256,FILES,'job-zombies','jobStartupRecipeSha256',
        'EXPERIMENTAL: 500,000 intended server script slots. Activation, game loading, AAE and friends remain unvalidated.')


def recipe() -> dict:
    return shared_recipe(fixed_recipe())


class JobSteam(LateSteam):
    # Use this wrapper for all job setup and removal. tools_root supports owned fixtures only.
    def __init__(self,manager: SteamPlay,*,tools_root: Path | None=None):
        super().__init__(manager,tools_root=tools_root,fixed=fixed_recipe())
        provider=manager.process_running
        manager.process_running=lambda name:provider(name) or any(provider(controller) for controller in CONTROLLERS)


if __name__=='__main__':
    try:raise SystemExit(shared_main(JobSteam,__doc__))
    except (PatchError,OSError,ValueError) as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
