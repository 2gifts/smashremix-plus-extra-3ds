/* Native translation of Fray's Falco/Phantasm.asm and Command.asm in Smash
 * Remix (pinned by remix/upstream.lock.json). This bring-up fixture registers
 * Falco at fkind 29; it is not a full-roster release or a MIPS interpreter. */
#include <ft/fighter.h>
#include <lb/lbreloc.h>
#include <sys/utils.h>
#include <string.h>
#include <stdlib.h>
#include "fighter_registry.h"
#include "native_remix_probe.h"
extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
extern alSoundEffect *func_800269C0_275C0(u16);
#include "falco_data.inc"

static float translation[4] = {1, 1, 1, 1};
static unsigned char direction[4][4];
static unsigned short hit_fgm[4][4];
static unsigned short hitlag_mul[4][4];
static unsigned short hit_di_mul[4][4];
static float victim_di_mul[4] = {1, 1, 1, 1};
static unsigned env_color[4];
static unsigned short pressed[4];
static FTStatusDesc falco_status[26];
static FTData falco_slot_data;
static void *falco_slot_files[9];
static s32 falco_slot_particle;
static s32 menu_count = ARRAY_COUNT(remix_menu_motions);
/* GFXRoutine.PHANTASM_BLUE: overlay, four-frame wait, end. */
static u32 phantasm_blue[] = {0x24000000, 0x00f0ffe0, 0x04000004, 0};
volatile unsigned native_remix_probe_ready;
volatile unsigned native_remix_probe_phantasm_ground;
volatile unsigned native_remix_probe_phantasm_air;

int nativeRelocIsFighterAnimation(unsigned int fid) {
    extern int nativeRemixDKUltIsAnimation(unsigned);
    extern int nativeRemixJPikaIsAnimation(unsigned);
    extern int nativeRemixEPikaIsAnimation(unsigned);
    extern int nativeRemixJMarioIsAnimation(unsigned);
    extern int nativeRemixJFalconIsAnimation(unsigned);
    extern int nativeRemixJLuigiIsAnimation(unsigned);
    extern int nativeRemixJDKIsAnimation(unsigned);
    /* Motion ID zero means no animation. Relocation file zero is the shared
     * menu artwork and must retain the normal sprite byte-order fixups. */
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_main_motions); i++)
        if (remix_main_motions[i].anim_file_id == fid &&
            !(remix_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_menu_motions); i++)
        if (remix_menu_motions[i].anim_file_id == fid &&
            !(remix_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return nativeRemixDKUltIsAnimation(fid) || nativeRemixJPikaIsAnimation(fid) || nativeRemixEPikaIsAnimation(fid) ||
           nativeRemixJMarioIsAnimation(fid) || nativeRemixJFalconIsAnimation(fid) ||
           nativeRemixJLuigiIsAnimation(fid) || nativeRemixJDKIsAnimation(fid);
}

void nativeRemixProbeReset(FTStruct *fp) {
    if (fp->player < 4) {
        translation[fp->player] = 1.0f;
        env_color[fp->player] = 0;
    }
}
unsigned nativeRemixProbeEnvColor(FTStruct *fp) {
    return fp->player < 4 ? env_color[fp->player] : 0;
}
float nativeRemixProbeTranslation(FTStruct *fp) {
    return fp->player < 4 ? translation[fp->player] : 1.0f;
}
void nativeRemixProbeHitboxReset(unsigned player, unsigned slot) {
    if (player < 4 && slot < 4) {
        direction[player][slot] = 0;
        hit_fgm[player][slot] = 0xffffu;
        hitlag_mul[player][slot] = 0xffffu;
        hit_di_mul[player][slot] = 0xffffu;
    }
}
unsigned nativeRemixProbeHitFgm(FTStruct *attacker, FTAttackColl *hit) {
    ptrdiff_t slot = hit - attacker->attack_colls;
    if (attacker->player >= 4 || slot < 0 || slot >= 4) return 0xffffu;
    return hit_fgm[attacker->player][slot];
}
void nativeRemixProbeDamageDirection(FTStruct *victim, FTStruct *attacker, FTAttackColl *hit) {
    ptrdiff_t slot = hit - attacker->attack_colls;
    if (attacker->player >= 4 || slot < 0 || slot >= 4) return;
    unsigned dir = direction[attacker->player][slot];
    if (dir == 1) victim->damage_lr = -attacker->lr;
    if (dir == 2) victim->damage_lr = attacker->lr;
}

static float upperHalfFloat(unsigned short half) {
    union { u32 u; float f; } value = {.u = (u32)half << 16};
    return value.f;
}

static void setHitMultiplier(unsigned short table[4][4], unsigned player,
                             unsigned flags, unsigned short value) {
    if (player >= 4) abort();
    if (flags >> 4) {
        for (unsigned i = 0; i < 4; i++) table[player][i] = value;
    } else {
        unsigned slot = flags & 0x0fu;
        if (slot >= 4) abort();
        table[player][slot] = value;
    }
}

void nativeRemixProbeApplyHitMultipliers(FTStruct *victim, FTStruct *attacker, FTAttackColl *hit) {
    if (victim->player < 4) victim_di_mul[victim->player] = 1.0f;
    if (!attacker || !hit || attacker->player >= 4) return;
    ptrdiff_t slot = hit - attacker->attack_colls;
    if (slot < 0 || slot >= 4) return;
    unsigned short lag = hitlag_mul[attacker->player][slot];
    unsigned short di = hit_di_mul[attacker->player][slot];
    /* The reference treats a negative upper-half float as "no override". */
    if (!(lag & 0x8000u)) {
        float multiplier = upperHalfFloat(lag);
        attacker->hitlag_mul = multiplier;
        victim->hitlag_mul = multiplier;
    }
    if (!(di & 0x8000u) && victim->player < 4)
        victim_di_mul[victim->player] = upperHalfFloat(di);
}

float nativeRemixProbeDiMultiplier(FTStruct *fp) {
    return fp->player < 4 ? victim_di_mul[fp->player] : 1.0f;
}

void nativeRemixProbeCommand(GObj *gobj, FTStruct *fp, FTMotionScript *ms) {
    u32 cmd = *(u32 *)ms->p_script;
    unsigned advance_words = 1;
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
    case 0xd1:
        fp->knockback_resist_status = value.f;
        break;
    case 0xd2:
        if (fp->player >= 4 || ((cmd >> 8) & 255) >= 4 || (cmd & 255) > 2) abort();
        direction[fp->player][(cmd >> 8) & 255] = cmd & 255;
        break;
    case 0xd3:
        if (fp->player < 4) translation[fp->player] = value.f;
        break;
    case 0xd4:
        fp->physics.vel_air.y = value.f;
        break;
    case 0xd5:
        fp->is_fastfall = (cmd & 0xffu) != 0;
        break;
    case 0xd6: {
        unsigned chance = (cmd >> 16) & 0xffu;
        unsigned type = (cmd >> 8) & 0xffu;
        unsigned count = cmd & 0xffu;
        if (!count || count > 64 || type > 1) abort();
        u32 *ids = PORT_RESOLVE(((u32 *)ms->p_script)[1]);
        if (!ids) abort();
        if (syUtilsRandIntRange(100) < chance) {
            unsigned index = syUtilsRandIntRange(count);
            unsigned word = ids[index / 2];
            unsigned fgm = (index & 1) ? word & 0xffffu : word >> 16;
            if (fgm != 0xffffu) {
                if (type) ftParamPlayVoice(fp, fgm);
                else func_800269C0_275C0(fgm);
            }
        }
        advance_words = 2;
        break;
    }
    case 0xd7:
        fp->ga = (cmd & 0xffu) != 0;
        fp->jumps_used = fp->ga ? 1 : 0;
        break;
    case 0xd8: {
        if (fp->player >= 4) abort();
        unsigned flags = (cmd >> 16) & 0xffu;
        unsigned fgm = cmd & 0xffffu;
        if (flags >> 4) {
            for (unsigned i = 0; i < 4; i++) hit_fgm[fp->player][i] = fgm;
        } else {
            unsigned slot = flags & 0x0fu;
            if (slot >= 4) abort();
            hit_fgm[fp->player][slot] = fgm;
        }
        break;
    }
    case 0xd9:
        if (fp->player < 4) env_color[fp->player] = ((u32 *)ms->p_script)[1];
        advance_words = 2;
        break;
    case 0xda:
        fp->lr = -fp->lr;
        break;
    case 0xdb: {
        FTData *data = fp->data;
        unsigned offset = cmd & 0xffffu;
        if ((offset & 3u) || !data || !data->p_file_mainmotion || !*data->p_file_mainmotion ||
            offset + 4u > lbRelocGetFileSize(data->file_mainmotion_id)) abort();
        ms->p_script = (u32 *)((u8 *)*data->p_file_mainmotion + offset);
        return;
    }
    case 0xdc: {
        unsigned fgm = (fp->input.pl.button_hold & fp->input.button_mask_l) ?
                       ((u32 *)ms->p_script)[1] & 0xffffu : cmd & 0xffffu;
        if (fgm != 0xffffu) ftParamPlayVoice(fp, fgm);
        advance_words = 2;
        break;
    }
    case 0xdd:
    case 0xde: {
        unsigned flags = (cmd >> 16) & 0xffu;
        unsigned short (*table)[4] = (cmd >> 24) == 0xdd ? hitlag_mul : hit_di_mul;
        setHitMultiplier(table, fp->player, flags, cmd & 0xffffu);
        break;
    }
    default:
        port_log("REMIX unported command %08lx\n", (unsigned long)cmd);
        abort();
    }
    ms->p_script = (u32 *)ms->p_script + advance_words;
}

/* The reference has a second command table for replaying effects when an
 * animation starts mid-script. It deliberately suppresses movement, random
 * sounds, color, facing reversal and alternate voice in that path. */
void nativeRemixProbeSeekCommand(GObj *gobj, FTStruct *fp, FTMotionScript *ms) {
    unsigned byte = *(u32 *)ms->p_script >> 24;
    if (byte == 0xd4 || byte == 0xd5 || byte == 0xda) {
        ms->p_script = (u32 *)ms->p_script + 1;
        return;
    }
    if (byte == 0xd6 || byte == 0xd9 || byte == 0xdc) {
        ms->p_script = (u32 *)ms->p_script + 2;
        return;
    }
    nativeRemixProbeCommand(gobj, fp, ms);
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
    for (unsigned player = 0; player < 4; player++)
        for (unsigned slot = 0; slot < 4; slot++) nativeRemixProbeHitboxReset(player, slot);
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindFox);
    /* Copy before changing any IDs or motion pointers. desc.ft_data points
     * at the live vanilla Fox row, which must remain unchanged for Fox. */
    falco_slot_data = *desc.ft_data;
    FTData *data = &falco_slot_data;
    memcpy(&data->file_main_id, remix_probe_files, sizeof(remix_probe_files));
    data->o_attributes = REMIX_PROBE_ATTRIBUTE_OFFSET;
    data->mainmotion = (FTMotionDescArray *)remix_main_motions;
    data->mainmotion_array_count = ARRAY_COUNT(remix_main_motions);
    data->submotion = (FTMotionDescArray *)remix_menu_motions;
    data->submotion_array_count = &menu_count;
    remix_relocate_scripts();
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
    /* Register Falco at the assembled mod's real fkind. The bottom-screen
     * VS selector chooses this independently backed row; Fox stays vanilla. */
    falco_slot_data.p_file_main = &falco_slot_files[0];
    falco_slot_data.p_file_mainmotion = &falco_slot_files[1];
    falco_slot_data.p_file_submotion = &falco_slot_files[2];
    falco_slot_data.p_file_model = &falco_slot_files[3];
    falco_slot_data.p_file_shieldpose = &falco_slot_files[4];
    falco_slot_data.p_file_special1 = &falco_slot_files[5];
    falco_slot_data.p_file_special2 = &falco_slot_files[6];
    falco_slot_data.p_file_special3 = &falco_slot_files[7];
    falco_slot_data.p_file_special4 = &falco_slot_files[8];
    falco_slot_data.p_particle = &falco_slot_particle;
    desc.ft_data = &falco_slot_data;
    port_fighter_register(29, &desc); /* Character.FALCO in the pinned ROM */
    native_remix_probe_ready = 1;
    port_log("REMIX PROBE: native Falco registered at fkind 29\n");
}
