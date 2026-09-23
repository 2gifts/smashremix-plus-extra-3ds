/* Shared registration for validated fighters that inherit vanilla gameplay
 * callbacks. Private motion scripts and file IDs are generated from the
 * pinned, assembled Remix reference. Custom moves stay in dedicated code. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);

typedef struct NativeRemixGenericDef {
    unsigned kind, parent;
    const u32 *file_ids;
    intptr_t attribute_offset;
    FTMotionDesc *main_motions;
    unsigned main_count;
    FTMotionDesc *menu_motions;
    s32 *menu_count;
    void (*relocate_scripts)(void);
} NativeRemixGenericDef;

typedef struct NativeRemixTablePatch {
    FTCostume *costume_row;
    s32 entry_status[2];
    s32 down_bounce_fgm;
} NativeRemixTablePatch;

typedef struct NativeRemixKirbyInhaleRow {
    u16 copy_id;
    s16 hat_id;
    f32 star_scale;
    s32 star_damage;
} NativeRemixKirbyInhaleRow;

typedef struct NativeRemixVictoryBGM {
    u16 fkind;
    s16 bgm_id;
} NativeRemixVictoryBGM;

#include "generic_variants_data.inc"
#include "native_kirby_inhale_rows.inc"
#include "native_victory_bgm_rows.inc"
typedef char NativeRemixTablePatchCountCheck[
    ARRAY_COUNT(native_remix_table_patches) == ARRAY_COUNT(native_remix_generic_defs) ? 1 : -1];

static FTData native_remix_generic_data[ARRAY_COUNT(native_remix_generic_defs)];
static void *native_remix_generic_files[ARRAY_COUNT(native_remix_generic_defs)][9];
static s32 native_remix_generic_particles[ARRAY_COUNT(native_remix_generic_defs)];

s32 nativeRemixKirbyStarDamage(unsigned fkind) {
    if (fkind < ARRAY_COUNT(native_remix_kirby_inhale_rows) &&
        native_remix_kirby_inhale_rows[fkind].star_damage > 0)
        return native_remix_kirby_inhale_rows[fkind].star_damage;
    return 17;
}

s32 nativeRemixVictoryBGM(unsigned fkind) {
    for (unsigned i = 0; i < ARRAY_COUNT(native_remix_victory_bgm); i++)
        if (native_remix_victory_bgm[i].fkind == fkind)
            return native_remix_victory_bgm[i].bgm_id;
    return -2; /* No compiled Remix override: use the original results path. */
}

static int has_animation(const FTMotionDesc *motions, unsigned count, unsigned fid) {
    for (unsigned i = 0; i < count; i++)
        if (motions[i].anim_file_id == fid &&
            !(motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

int nativeRemixGenericIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(native_remix_generic_defs); i++) {
        const NativeRemixGenericDef *def = &native_remix_generic_defs[i];
        if (has_animation(def->main_motions, def->main_count, fid) ||
            has_animation(def->menu_motions, *def->menu_count, fid)) return 1;
    }
    return 0;
}

void nativeRemixGenericInit(void) {
    for (unsigned i = 0; i < ARRAY_COUNT(native_remix_generic_defs); i++) {
        const NativeRemixGenericDef *def = &native_remix_generic_defs[i];
        FighterDescriptor desc = *port_fighter_descriptor(def->parent);
        FTData *data = &native_remix_generic_data[i];
        void **files = native_remix_generic_files[i];
        *data = *desc.ft_data;
        memcpy(&data->file_main_id, def->file_ids, sizeof(native_remix_generic_files[i]));
        data->o_attributes = def->attribute_offset;
        data->mainmotion = (FTMotionDescArray *)def->main_motions;
        data->mainmotion_array_count = def->main_count;
        data->submotion = (FTMotionDescArray *)def->menu_motions;
        data->submotion_array_count = def->menu_count;
        data->p_file_main = &files[0];
        data->p_file_mainmotion = &files[1];
        data->p_file_submotion = &files[2];
        data->p_file_model = &files[3];
        data->p_file_shieldpose = &files[4];
        data->p_file_special1 = &files[5];
        data->p_file_special2 = &files[6];
        data->p_file_special3 = &files[7];
        data->p_file_special4 = &files[8];
        data->p_particle = &native_remix_generic_particles[i];
        desc.ft_data = data;
        desc.costume_row = native_remix_table_patches[i].costume_row;
        desc.entry_appear_status[0] = native_remix_table_patches[i].entry_status[0];
        desc.entry_appear_status[1] = native_remix_table_patches[i].entry_status[1];
        desc.down_bounce_fgm = native_remix_table_patches[i].down_bounce_fgm;
        def->relocate_scripts();
        port_fighter_register(def->kind, &desc);
        port_log("REMIX PROBE: generic fighter registered at fkind %u\n", def->kind);
    }
}
