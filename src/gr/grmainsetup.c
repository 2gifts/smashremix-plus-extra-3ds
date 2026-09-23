#include <gr/ground.h>
#include <sc/scene.h>

#ifdef SSB_REMIX_PROBE
#include <native_remix_stages.h>
#include <stdlib.h>
#endif

// // // // // // // // // // // //
//                               //
//       INITIALIZED DATA        //
//                               //
// // // // // // // // // // // //

// 0x8012E840
GObj* (*dGRMainSetupProcMakeList[/* */])(void) =
{
    grCastleMakeGround,
    grSectorMakeGround,
    grJungleMakeGround,
    grZebesMakeGround,
    grHyruleMakeGround,
    grYosterMakeGround,
    grPupupuMakeGround,
    grYamabukiMakeGround,
    grInishieMakeGround
};

// // // // // // // // // // // //
//                               //
//           FUNCTIONS           //
//                               //
// // // // // // // // // // // //

// 0x801056C0
void grMainSetupMakeGround(void)
{
#ifdef SSB_REMIX_PROBE
    if (gSCManagerBattleState->gkind > nGRKindBonus2End)
    {
        const NativeRemixStageRecord *stage = nativeRemixStageGet(gSCManagerBattleState->gkind);
        if (stage == NULL || stage->setup_kind == 255)
        {
            abort(); /* A custom N64 hazard routine cannot run on ARM. */
        }
        if (stage->setup_kind != 0)
        {
            dGRMainSetupProcMakeList[stage->setup_kind - 1]();
        }
        return;
    }
#endif
    if (gSCManagerBattleState->gkind <= nGRKindBattleEnd)
    {
        dGRMainSetupProcMakeList[gSCManagerBattleState->gkind]();
    }
    else if (gSCManagerBattleState->gkind == nGRKindBonus3)
    {
        grBonus3MakeGround();
    }
    else if (gSCManagerBattleState->gkind >= nGRKindBonus2Start)
    {
        sc1PBonusStageInitBonus2();
    }
    else if (gSCManagerBattleState->gkind >= nGRKindBonus1Start)
    {
        sc1PBonusStageMakeBonus1Ground();
    }
}
