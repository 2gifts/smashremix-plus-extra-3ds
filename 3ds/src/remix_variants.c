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

#include "generic_variants_data.inc"

static FTData native_remix_generic_data[ARRAY_COUNT(native_remix_generic_defs)];
static void *native_remix_generic_files[ARRAY_COUNT(native_remix_generic_defs)][9];
static s32 native_remix_generic_particles[ARRAY_COUNT(native_remix_generic_defs)];

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
        def->relocate_scripts();
        port_fighter_register(def->kind, &desc);
        port_log("REMIX PROBE: generic fighter registered at fkind %u\n", def->kind);
    }
}
