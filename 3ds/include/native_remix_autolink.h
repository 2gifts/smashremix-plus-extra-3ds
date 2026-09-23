#ifndef NATIVE_REMIX_AUTOLINK_H
#define NATIVE_REMIX_AUTOLINK_H

/* Native translation of +EXTRA's AutolinkAngle.set_hit_angle hook. The input
 * coordinates are world-space hitbox and fighter positions. Only airborne
 * fighter hits with angle 362 and knockback below 80 take the costly path. */
#include <math.h>

typedef struct NativeRemixAutolinkResult {
    int angle;
    float knockback;
} NativeRemixAutolinkResult;

static inline NativeRemixAutolinkResult nativeRemixAutolinkAngle(
    int angle, float knockback, int attacker_air, int victim_air,
    float attacker_vel_x, float attacker_vel_y,
    float hit_x, float hit_y, float victim_x, float victim_y,
    float attacker_x)
{
    NativeRemixAutolinkResult result = {angle, knockback};
    if (angle != 362 || !attacker_air || !(knockback < 80.0f))
        return result;
    if (!victim_air) {
        result.angle = 80;
        return result;
    }

    /* The assembly loads 0x3D270000, not an exact decimal 0.04. */
    const float offset_scale = 0.040771484375f;
    float offset_x = (hit_x - victim_x) * offset_scale;
    float offset_y = (hit_y - victim_y) * offset_scale;
    float aim_x = attacker_vel_x + offset_x;
    float aim_y = attacker_vel_y + offset_y;
    result.knockback = sqrtf(attacker_vel_x * attacker_vel_x +
                             attacker_vel_y * attacker_vel_y) +
                       sqrtf(offset_x * offset_x + offset_y * offset_y);
    if (victim_x < attacker_x)
        aim_x = -aim_x;
    result.angle = (int)nearbyintf(atan2f(aim_y, aim_x) * 57.295780181884766f);
    return result;
}

#endif
