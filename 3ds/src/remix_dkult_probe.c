/* Native translation of DK Ult's special hooks in +EXTRA 0.6.0. The motion
 * table is generated locally from the pinned reference ROM. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "dkult_data.inc"

enum {
    DK_SPECIAL_FIRST = nFTCommonStatusSpecialStart,
    DK_SPECIAL_LAST = nFTDonkeyStatusHeavyThrowB4,
    DK_SPECIAL_COUNT = DK_SPECIAL_LAST - DK_SPECIAL_FIRST + 1,
    DKULT_SPECIAL_AIR_LW = DK_SPECIAL_LAST + 1
};
_Static_assert(DK_SPECIAL_COUNT == 30, "DK Ult status table must follow vanilla Donkey");

static FTStatusDesc dkult_status[DK_SPECIAL_COUNT + 1];
static FTData dkult_data;
static void *dkult_files[9];
static s32 dkult_particle;

int nativeRemixDKUltIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_dkult_main_motions); i++)
        if (remix_dkult_main_motions[i].anim_file_id == fid &&
            !(remix_dkult_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_dkult_menu_motions); i++)
        if (remix_dkult_menu_motions[i].anim_file_id == fid &&
            !(remix_dkult_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

static void dkultStartUpdate(GObj *gobj) {
    FTStruct *fp = ftGetStruct(gobj);
    ftAnimEndCheckSetStatus(gobj, fp->passive_vars.donkey.charge_level == FTDONKEY_GIANTPUNCH_CHARGE_MAX ?
                            ftDonkeySpecialNEndSetStatus : ftDonkeySpecialNLoopSetStatus);
}

static void dkultAirStartUpdate(GObj *gobj) {
    FTStruct *fp = ftGetStruct(gobj);
    ftAnimEndCheckSetStatus(gobj, fp->passive_vars.donkey.charge_level == FTDONKEY_GIANTPUNCH_CHARGE_MAX ?
                            ftDonkeySpecialAirNEndSetStatus : ftDonkeySpecialAirNLoopSetStatus);
}

static void dkultLoopUpdate(GObj *gobj) {
    FTStruct *fp = ftGetStruct(gobj);
    ftDonkeySpecialNLoopProcUpdate(gobj);
    if (fp->status_id != nFTDonkeyStatusSpecialNLoop && fp->status_id != nFTDonkeyStatusSpecialAirNLoop) return;
    /* +EXTRA speeds the charging animation up as the punch approaches ten
     * charges. Keep the original Donkey charge/interrupt callback above. */
    gcSetAnimSpeed(gobj, 12.0f / (14.0f - 0.7f * fp->passive_vars.donkey.charge_level));
}

static void dkultHiPhysics(GObj *gobj) {
    FTStruct *fp = ftGetStruct(gobj);
    if (gobj->anim_frame < 62.0f && fp->input.pl.stick_range.x * fp->lr >= 0)
        ftPhysicsApplyClampGroundVelStickRange(fp, 0, 0.5f, 30.0f);
    ftPhysicsSetGroundVelFriction(fp, 1.0f);
    ftPhysicsSetGroundVelTransferAir(gobj);
}

static void dkultAirLwSetStatus(GObj *gobj) {
    ftMainSetStatus(gobj, DKULT_SPECIAL_AIR_LW, 0.0f, 1.0f, FTSTATUS_PRESERVE_NONE);
    ftMainPlayAnimEventsAll(gobj);
}

void nativeRemixDKUltInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindDonkey);
    dkult_data = *desc.ft_data;
    memcpy(&dkult_data.file_main_id, remix_dkult_files, sizeof(remix_dkult_files));
    dkult_data.o_attributes = REMIX_DKULT_ATTRIBUTE_OFFSET;
    dkult_data.mainmotion = (FTMotionDescArray *)remix_dkult_main_motions;
    dkult_data.mainmotion_array_count = ARRAY_COUNT(remix_dkult_main_motions);
    dkult_data.submotion = (FTMotionDescArray *)remix_dkult_menu_motions;
    dkult_data.submotion_array_count = &remix_dkult_menu_count;
    dkult_data.p_file_main = &dkult_files[0];
    dkult_data.p_file_mainmotion = &dkult_files[1];
    dkult_data.p_file_submotion = &dkult_files[2];
    dkult_data.p_file_model = &dkult_files[3];
    dkult_data.p_file_shieldpose = &dkult_files[4];
    dkult_data.p_file_special1 = &dkult_files[5];
    dkult_data.p_file_special2 = &dkult_files[6];
    dkult_data.p_file_special3 = &dkult_files[7];
    dkult_data.p_file_special4 = &dkult_files[8];
    dkult_data.p_particle = &dkult_particle;
    desc.ft_data = &dkult_data;

    remix_dkult_relocate_scripts();
    memcpy(dkult_status, desc.special_descs, sizeof(dkult_status[0]) * DK_SPECIAL_COUNT);
    dkult_status[nFTDonkeyStatusSpecialNStart - DK_SPECIAL_FIRST].proc_update = dkultStartUpdate;
    dkult_status[nFTDonkeyStatusSpecialAirNStart - DK_SPECIAL_FIRST].proc_update = dkultAirStartUpdate;
    dkult_status[nFTDonkeyStatusSpecialNLoop - DK_SPECIAL_FIRST].proc_update = dkultLoopUpdate;
    dkult_status[nFTDonkeyStatusSpecialAirNLoop - DK_SPECIAL_FIRST].proc_update = dkultLoopUpdate;
    dkult_status[nFTDonkeyStatusSpecialHi - DK_SPECIAL_FIRST].proc_physics = dkultHiPhysics;
    dkult_status[DK_SPECIAL_COUNT] = (FTStatusDesc) {
        { ARRAY_COUNT(remix_dkult_main_motions) - 1, nFTMotionAttackIDNone },
        { .halfword = 0 }, ftAnimEndSetFall, NULL,
        ftPhysicsApplyAirVelDrift, mpCommonProcFighterCliffFloorCeil
    };
    desc.special_descs = dkult_status;
    desc.special_descs_count = ARRAY_COUNT(dkult_status);
    desc.special_handler[PORT_FIGHTER_SPECIAL_AIR_LW] = dkultAirLwSetStatus;
    port_fighter_register(81, &desc); /* Character.DKULT in the pinned ROM */
    port_log("REMIX PROBE: native DK Ult registered at fkind 81\n");
}
