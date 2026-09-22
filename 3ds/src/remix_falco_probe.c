/* Native translation of Fray's Falco/Phantasm.asm and Command.asm in Smash
 * Remix (pinned by remix/upstream.lock.json). This bring-up fixture replaces
 * the Fox slot; it is not a full-roster release or a MIPS interpreter. */
#include <ft/fighter.h>
#include <string.h>
#include <stdlib.h>
#include "fighter_registry.h"
#include "native_remix_probe.h"
extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "falco_data.inc"

static float translation[4] = {1, 1, 1, 1};
static unsigned char direction[4][4];
static unsigned short pressed[4];
static FTStatusDesc falco_status[26];
static s32 menu_count = ARRAY_COUNT(remix_menu_motions);
/* GFXRoutine.PHANTASM_BLUE: overlay, four-frame wait, end. */
static u32 phantasm_blue[] = {0x24000000, 0x00f0ffe0, 0x04000004, 0};
volatile unsigned native_remix_probe_ready;
volatile unsigned native_remix_probe_phantasm_ground;
volatile unsigned native_remix_probe_phantasm_air;

int nativeRelocIsFighterAnimation(unsigned int fid) {
    /* Motion ID zero means no animation. Relocation file zero is the shared
     * menu artwork and must retain the normal sprite byte-order fixups. */
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_main_motions); i++)
        if (remix_main_motions[i].anim_file_id == fid &&
            !(remix_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_menu_motions); i++)
        if (remix_menu_motions[i].anim_file_id == fid &&
            !(remix_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixProbeReset(FTStruct *fp) {
    if (fp->player < 4) translation[fp->player] = 1.0f;
}
float nativeRemixProbeTranslation(FTStruct *fp) {
    return fp->player < 4 ? translation[fp->player] : 1.0f;
}
void nativeRemixProbeHitboxReset(unsigned player, unsigned slot) {
    if (player < 4 && slot < 4) direction[player][slot] = 0;
}
void nativeRemixProbeDamageDirection(FTStruct *victim, FTStruct *attacker, FTAttackColl *hit) {
    ptrdiff_t slot = hit - attacker->attack_colls;
    if (attacker->player >= 4 || slot < 0 || slot >= 4) return;
    unsigned dir = direction[attacker->player][slot];
    if (dir == 1) victim->damage_lr = -attacker->lr;
    if (dir == 2) victim->damage_lr = attacker->lr;
}

void nativeRemixProbeCommand(GObj *gobj, FTStruct *fp, FTMotionScript *ms) {
    u32 cmd = *(u32 *)ms->p_script;
    union { u32 u; float f; } value = {.u = (cmd & 0xffffu) << 16};
    switch (cmd >> 24) {
    case 0xd0: {
        DObj *root = DObjGetStruct(gobj);
        float old_speed = root->anim_speed;
        gcSetAnimSpeed(gobj, value.f);
        if (cmd & 0x00ff0000u) {
            /* Preserve script timing; the tiny sentinel restores normal speed
             * at the next action even if the root was exactly 1.0. */
            root->anim_speed = old_speed == 1.0f ? 0x1.000002p0f : old_speed;
        }
        break;
    }
    case 0xd2:
        if (fp->player >= 4 || ((cmd >> 8) & 255) >= 4 || (cmd & 255) > 2) abort();
        direction[fp->player][(cmd >> 8) & 255] = cmd & 255;
        break;
    case 0xd3:
        if (fp->player < 4) translation[fp->player] = value.f;
        break;
    default:
        port_log("REMIX unported command %08lx\n", (unsigned long)cmd);
        abort();
    }
    ms->p_script = (u32 *)ms->p_script + 1;
}

static unsigned bufferButtons(FTStruct *fp) {
    if (fp->player >= 4) return 0;
    unsigned now = fp->input.pl.button_tap;
    unsigned both = now | pressed[fp->player];
    pressed[fp->player] = now;
    return both & fp->input.button_mask_b;
}
static void stopHitboxes(GObj *gobj) {
    FTStruct *fp = ftGetStruct(gobj);
    fp->is_use_fogcolor = FALSE;
    ftParamClearAttackCollAll(gobj);
}
static void groundPhantasm(GObj *gobj) {
    FTStruct *fp = ftGetStruct(gobj);
    unsigned shorten = bufferButtons(fp);
    native_remix_probe_phantasm_ground++;
    if (fp->motion_vars.flags.flag2 == 2) {
        fp->physics.vel_ground.x = 460.0f;
        if (shorten) fp->motion_vars.flags.flag2 = 3;
    }
    if (fp->motion_vars.flags.flag2 == 3) {
        fp->physics.vel_ground.x = 60.0f;
        fp->motion_vars.flags.flag2 = 0;
        stopHitboxes(gobj);
    }
}
static void airPhantasm(GObj *gobj) {
    FTStruct *fp = ftGetStruct(gobj);
    unsigned shorten = bufferButtons(fp);
    native_remix_probe_phantasm_air++;
    int phase = fp->motion_vars.flags.flag2;
    int original_phase = phase;
    if (phase == 1) {
        fp->is_fastfall = FALSE;
        fp->physics.vel_air.x = 0.0f;
        fp->physics.vel_air.y = 50.0f;
    }
    if (phase == 3) {
        fp->physics.vel_air.x = 460.0f * fp->lr;
        if (shorten) fp->motion_vars.flags.flag2 = phase = 4;
    }
    if (phase == 2 || phase == 3) fp->physics.vel_air.y = fp->attr->gravity;
    if (phase == 4) {
        fp->physics.vel_air.x = 30.0f * fp->lr;
        fp->motion_vars.flags.flag2 = phase = 5;
        stopHitboxes(gobj);
    }
    /* Upstream tests its original phase register, so slow-fall starts on the
     * following frame when the dash first ends. */
    if (original_phase == 5) fp->physics.vel_air.y += 0x1.9ap0f; /* 0x3FCD0000 */
}
static void airPhysics(GObj *gobj) {
    if (ftGetStruct(gobj)->motion_vars.flags.flag2 == 5) ftPhysicsApplyAirVelDrift(gobj);
    else ftPhysicsApplyAirVelFriction(gobj);
}
static void airMap(GObj *gobj) {
    FTStruct *fp = ftGetStruct(gobj);
    if (fp->ga == nMPKineticsAir) {
        if (fp->motion_vars.flags.flag1 == 0 || fp->physics.vel_air.y >= 0.0f)
            mpCommonCheckFighterProject(gobj);
        else if (mpCommonCheckFighterPassCliff(gobj, ftMarioSpecialHiProcPass)) {
            if (fp->coll_data.mask_stat & MAP_FLAG_CLIFF_MASK) ftCommonCliffCatchSetStatus(gobj);
            else ftCommonLandingFallSpecialSetStatus(gobj, FALSE, 0x1.66p-2f); /* 0x3EB30000 */
        }
    } else mpCommonSetFighterFallOnEdgeBreak(gobj);
}
static void neutral(GObj *gobj, int air) {
    FTStruct *fp = ftGetStruct(gobj);
    ftMainSetStatus(gobj, air ? nFTFoxStatusSpecialAirN : nFTFoxStatusSpecialN,
                    0.0f, 1.0f, air ? FTSTATUS_PRESERVE_FASTFALL : FTSTATUS_PRESERVE_NONE);
    ftMainPlayAnimEventsAll(gobj);
    fp->motion_vars.flags.flag0 = fp->motion_vars.flags.flag1 = 0;
    fp->motion_vars.flags.flag2 = 1;
}
static void groundNeutral(GObj *gobj) { neutral(gobj, 0); }
static void airNeutral(GObj *gobj) { neutral(gobj, 1); }

void nativeRemixProbeInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindFox);
    FTData *data = desc.ft_data;
    memcpy(&data->file_main_id, remix_probe_files, sizeof(remix_probe_files));
    data->o_attributes = REMIX_PROBE_ATTRIBUTE_OFFSET;
    data->mainmotion = (FTMotionDescArray *)remix_main_motions;
    data->mainmotion_array_count = ARRAY_COUNT(remix_main_motions);
    data->submotion = (FTMotionDescArray *)remix_menu_motions;
    data->submotion_array_count = &menu_count;
    remix_probe_relocate_scripts();
    dGMColScriptsDescs[98] = (GMColDesc){phantasm_blue, 100, TRUE};
    memcpy(falco_status, desc.special_descs, sizeof(falco_status));
    falco_status[0xe1 - 0xdc].proc_update = ftAnimEndSetWait;
    falco_status[0xe1 - 0xdc].proc_interrupt = groundPhantasm;
    falco_status[0xe2 - 0xdc].proc_update = ftFoxSpecialAirHiEndProcUpdate;
    falco_status[0xe2 - 0xdc].proc_interrupt = airPhantasm;
    falco_status[0xe2 - 0xdc].proc_physics = airPhysics;
    falco_status[0xe2 - 0xdc].proc_map = airMap;
    desc.special_descs = falco_status;
    desc.special_descs_count = ARRAY_COUNT(falco_status);
    desc.special_handler[PORT_FIGHTER_SPECIAL_N] = groundNeutral;
    desc.special_handler[PORT_FIGHTER_SPECIAL_AIR_N] = airNeutral;
    desc.scale = 1.2f;
    port_fighter_register(nFTKindFox, &desc);
    native_remix_probe_ready = 1;
    port_log("REMIX PROBE: native Falco registered in Fox slot\n");
}
