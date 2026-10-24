#pragma once

#include <cstdint>
#include <cstddef>
#include <arm_neon.h>

namespace neon {

// ============================================================================
// Frustum Culling - NEON optimized for Cortex-A57 (Tegra X1)
// ============================================================================
// Features:
// - AABB vs Frustum (4 AABBs at once)
// - Sphere vs Frustum (4 spheres at once)
// - OBB vs Frustum (via separating axis)
// - Cone vs Frustum (spot lights)
// - BVH traversal helpers
// - View frustum from view-proj matrix
// ============================================================================

// ---------------------------------------------------------------------------
// Frustum representation
// ---------------------------------------------------------------------------
// 6 planes: Left, Right, Bottom, Top, Near, Far
// Plane: normal (x,y,z) + distance (w)  =>  normal·point + distance > 0 = inside

struct Frustum {
    float32x4_t planes[6];  // each: {nx, ny, nz, d}
    
    // Build from View-Projection matrix (column-major)
    static Frustum from_viewproj(const float* vp) {
        Frustum f;
        // Left:   col3 + col0
        // Right:  col3 - col0
        // Bottom: col3 + col1
        // Top:    col3 - col1
        // Near:   col3 + col2
        // Far:    col3 - col2
        
        float32x4_t c0 = vld1q_f32(vp + 0);   // column 0
        float32x4_t c1 = vld1q_f32(vp + 4);   // column 1
        float32x4_t c2 = vld1q_f32(vp + 8);   // column 2
        float32x4_t c3 = vld1q_f32(vp + 12);  // column 3
        
        f.planes[0] = vaddq_f32(c3, c0);  // Left
        f.planes[1] = vsubq_f32(c3, c0);  // Right
        f.planes[2] = vaddq_f32(c3, c1);  // Bottom
        f.planes[3] = vsubq_f32(c3, c1);  // Top
        f.planes[4] = vaddq_f32(c3, c2);  // Near
        f.planes[5] = vsubq_f32(c3, c2);  // Far
        
        // Normalize planes (optional, but helps with distance accuracy)
        for (int i = 0; i < 6; ++i) {
            float32x4_t n = f.planes[i];
            float32x4_t len_sq = vmulq_f32(n, n);
            len_sq = vpaddq_f32(len_sq, len_sq);
            len_sq = vpaddq_f32(len_sq, len_sq);
            float len = vgetq_lane_f32(vsqrtq_f32(len_sq), 0);
            if (len > 1e-6f) {
                f.planes[i] = vdivq_n_f32(n, len);
            }
        }
        return f;
    }
    
    // Build from view + proj separately
    static Frustum from_view_proj(const float* view, const float* proj) {
        float vp[16];
        // Multiply proj * view (column-major)
        for (int r = 0; r < 4; ++r) {
            for (int c = 0; c < 4; ++c) {
                float sum = 0;
                for (int k = 0; k < 4; ++k) {
                    sum += proj[c*4+k] * view[k*4+r];
                }
                vp[c*4+r] = sum;
            }
        }
        return from_viewproj(vp);
    }
};

// ---------------------------------------------------------------------------
// AABB vs Frustum - 4 AABBs at once
// ---------------------------------------------------------------------------
// AABB: min (x,y,z), max (x,y,z)
// Inside if: for all planes, max·normal + d > 0 (for at least one corner)
// Optimized: test max corner for positive normal, min for negative

struct AABB4 {
    float32x4_t min_x, min_y, min_z;
    float32x4_t max_x, max_y, max_z;
};

// Result: 4-bit mask (1 = inside/visible, 0 = culled)
inline uint32x4_t neon_aabb4_vs_frustum(const Frustum& frustum, const AABB4& aabb) {
    uint32x4_t visible = vdupq_n_u32(0xFFFFFFFF);
    
    for (int p = 0; p < 6; ++p) {
        float32x4_t plane = frustum.planes[p];
        float32x4_t nx = vdupq_laneq_f32(plane, 0);
        float32x4_t ny = vdupq_laneq_f32(plane, 1);
        float32x4_t nz = vdupq_laneq_f32(plane, 2);
        float32x4_t d  = vdupq_laneq_f32(plane, 3);
        
        // Select corner: max if normal > 0, else min
        float32x4_t cx = vbslq_f32(vcgtq_f32(nx, vdupq_n_f32(0)), aabb.max_x, aabb.min_x);
        float32x4_t cy = vbslq_f32(vcgtq_f32(ny, vdupq_n_f32(0)), aabb.max_y, aabb.min_y);
        float32x4_t cz = vbslq_f32(vcgtq_f32(nz, vdupq_n_f32(0)), aabb.max_z, aabb.min_z);
        
        // distance = nx*cx + ny*cy + nz*cz + d
        float32x4_t dist = vmlaq_f32(vmlaq_f32(vmlaq_f32(d, nx, cx), ny, cy), nz, cz);
        
        // Inside if dist > 0
        uint32x4_t plane_visible = vcgtq_f32(dist, vdupq_n_f32(0));
        visible = vandq_u32(visible, plane_visible);
        
        // Early exit if all culled
        if (vgetq_lane_u32(visible, 0) == 0 &&
            vgetq_lane_u32(visible, 1) == 0 &&
            vgetq_lane_u32(visible, 2) == 0 &&
            vgetq_lane_u32(visible, 3) == 0) {
            break;
        }
    }
    return visible;
}

// Scalar helper to extract individual results
inline bool aabb_visible(const uint32x4_t& result, int index) {
    return vgetq_lane_u32(result, index) != 0;
}

// ---------------------------------------------------------------------------
// Sphere vs Frustum - 4 spheres at once
// ---------------------------------------------------------------------------

struct Sphere4 {
    float32x4_t center_x, center_y, center_z;
    float32x4_t radius;
};

inline uint32x4_t neon_sphere4_vs_frustum(const Frustum& frustum, const Sphere4& sphere) {
    uint32x4_t visible = vdupq_n_u32(0xFFFFFFFF);
    
    for (int p = 0; p < 6; ++p) {
        float32x4_t plane = frustum.planes[p];
        float32x4_t nx = vdupq_laneq_f32(plane, 0);
        float32x4_t ny = vdupq_laneq_f32(plane, 1);
        float32x4_t nz = vdupq_laneq_f32(plane, 2);
        float32x4_t d  = vdupq_laneq_f32(plane, 3);
        
        // Distance from center to plane
        float32x4_t dist = vmlaq_f32(vmlaq_f32(vmlaq_f32(d, nx, sphere.center_x), ny, sphere.center_y), nz, sphere.center_z);
        
        // Visible if dist > -radius
        uint32x4_t plane_visible = vcgtq_f32(dist, vnegq_f32(sphere.radius));
        visible = vandq_u32(visible, plane_visible);
        
        if (vgetq_lane_u32(visible, 0) == 0 &&
            vgetq_lane_u32(visible, 1) == 0 &&
            vgetq_lane_u32(visible, 2) == 0 &&
            vgetq_lane_u32(visible, 3) == 0) break;
    }
    return visible;
}

// ---------------------------------------------------------------------------
// AABB vs Frustum (single) - for CPU fallback / small counts
// ---------------------------------------------------------------------------

inline bool neon_aabb_vs_frustum(const Frustum& frustum,
                                  const float* min, const float* max) {
    for (int p = 0; p < 6; ++p) {
        float nx = frustum.planes[p][0];
        float ny = frustum.planes[p][1];
        float nz = frustum.planes[p][2];
        float d  = frustum.planes[p][3];
        
        float cx = (nx >= 0) ? max[0] : min[0];
        float cy = (ny >= 0) ? max[1] : min[1];
        float cz = (nz >= 0) ? max[2] : min[2];
        
        float dist = nx*cx + ny*cy + nz*cz + d;
        if (dist <= 0) return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// OBB vs Frustum (via Separating Axis Theorem)
// ---------------------------------------------------------------------------
// OBB: center + 3 axes (normalized) + 3 half-extents

struct OBB {
    float32x4_t center;      // x,y,z,0
    float32x4_t axis_x;      // x,y,z,0
    float32x4_t axis_y;      // x,y,z,0
    float32x4_t axis_z;      // x,y,z,0
    float32x4_t half_extent; // hx,hy,hz,0
};

inline bool neon_obb_vs_frustum(const Frustum& frustum, const OBB& obb) {
    // For each frustum plane, compute projected radius
    // r = hx*|axis_x·n| + hy*|axis_y·n| + hz*|axis_z·n|
    // Distance = center·n + d
    // Inside if distance > -r
    
    for (int p = 0; p < 6; ++p) {
        float32x4_t plane = frustum.planes[p];
        float32x4_t n = {plane[0], plane[1], plane[2], 0};
        float d = plane[3];
        
        // Project half-extents onto plane normal
        float32x4_t dot_x = vmulq_f32(obb.axis_x, n);
        float32x4_t dot_y = vmulq_f32(obb.axis_y, n);
        float32x4_t dot_z = vmulq_f32(obb.axis_z, n);
        
        dot_x = vabsq_f32(dot_x);
        dot_y = vabsq_f32(dot_y);
        dot_z = vabsq_f32(dot_z);
        
        float32x4_t r = vmlaq_f32(vmulq_f32(obb.half_extent, dot_x), obb.half_extent, dot_y);
        r = vmlaq_f32(r, obb.half_extent, dot_z);
        
        float32x4_t center_dist = vmlaq_f32(vdupq_laneq_f32(plane, 3), n, obb.center);
        
        // Sum components
        float dist_sum = vgetq_lane_f32(center_dist, 0) + vgetq_lane_f32(center_dist, 1) + vgetq_lane_f32(center_dist, 2);
        float r_sum = vgetq_lane_f32(r, 0) + vgetq_lane_f32(r, 1) + vgetq_lane_f32(r, 2);
        
        if (dist_sum + r_sum <= 0) return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// Cone vs Frustum (Spot Light Culling)
// ---------------------------------------------------------------------------
// Cone: apex, direction (normalized), cos(angle), range

struct Cone {
    float32x4_t apex;        // x,y,z,0
    float32x4_t direction;   // x,y,z,0 (normalized)
    float32x4_t cos_angle;   // cos(half_angle), 0,0,0
    float32x4_t range;       // max_distance, 0,0,0
};

inline bool neon_cone_vs_frustum(const Frustum& frustum, const Cone& cone) {
    // Conservative: treat cone as sphere at apex + direction*range with radius = range*sin(angle)
    float sin_angle = sqrtf(1.0f - vgetq_lane_f32(cone.cos_angle, 0) * vgetq_lane_f32(cone.cos_angle, 0));
    float sphere_radius = vgetq_lane_f32(cone.range, 0) * sin_angle;
    float32x4_t sphere_center = vmlaq_f32(cone.apex, cone.direction, cone.range);
    
    Sphere4 sphere;
    sphere.center_x = vdupq_laneq_f32(sphere_center, 0);
    sphere.center_y = vdupq_laneq_f32(sphere_center, 1);
    sphere.center_z = vdupq_laneq_f32(sphere_center, 2);
    sphere.radius = vdupq_n_f32(sphere_radius);
    
    uint32x4_t result = neon_sphere4_vs_frustum(frustum, sphere);
    return vgetq_lane_u32(result, 0) != 0;
}

// ---------------------------------------------------------------------------
// BVH Node for hierarchical culling
// ---------------------------------------------------------------------------

struct BVHNode {
    float32x4_t min_bounds;  // min_x, min_y, min_z, 0
    float32x4_t max_bounds;  // max_x, max_y, max_z, 0
    int left_child;          // -1 if leaf
    int right_child;
    int first_primitive;     // for leaf
    int primitive_count;
};

// Traverse BVH with frustum - returns visible primitive indices
inline void neon_bvh_traverse_frustum(
    const Frustum& frustum,
    const BVHNode* nodes,
    int node_count,
    int root_index,
    int* visible_primitives,
    int& visible_count,
    int max_primitives
) {
    // Stack-based traversal
    int stack[64];
    int stack_top = 0;
    stack[stack_top++] = root_index;
    
    AABB4 aabb4;
    
    while (stack_top > 0) {
        int node_idx = stack[--stack_top];
        const BVHNode& node = nodes[node_idx];
        
        // Load AABB
        aabb4.min_x = vdupq_laneq_f32(node.min_bounds, 0);
        aabb4.min_y = vdupq_laneq_f32(node.min_bounds, 1);
        aabb4.min_z = vdupq_laneq_f32(node.min_bounds, 2);
        aabb4.max_x = vdupq_laneq_f32(node.max_bounds, 0);
        aabb4.max_y = vdupq_laneq_f32(node.max_bounds, 1);
        aabb4.max_z = vdupq_laneq_f32(node.max_bounds, 2);
        
        uint32x4_t visible = neon_aabb4_vs_frustum(frustum, aabb4);
        
        // Check each lane (we only use lane 0 for single AABB)
        if (vgetq_lane_u32(visible, 0) == 0) continue; // Culled
        
        if (node.left_child == -1) {
            // Leaf - add primitives
            for (int i = 0; i < node.primitive_count && visible_count < max_primitives; ++i) {
                visible_primitives[visible_count++] = node.first_primitive + i;
            }
        } else {
            // Internal - push children
            stack[stack_top++] = node.right_child;
            stack[stack_top++] = node.left_child;
        }
    }
}

// ---------------------------------------------------------------------------
// Batch culling for render queue
// ---------------------------------------------------------------------------

struct RenderObject {
    float32x4_t bounds_min;
    float32x4_t bounds_max;
    uint32_t material_id;
    uint32_t mesh_id;
    uint32_t instance_data_offset;
    uint32_t flags;
};

inline int neon_cull_render_objects(
    const Frustum& frustum,
    const RenderObject* objects,
    int count,
    RenderObject* visible_objects,
    int max_visible
) {
    int visible_count = 0;
    AABB4 aabb4;
    
    for (int i = 0; i < count && visible_count < max_visible; ++i) {
        const RenderObject& obj = objects[i];
        
        aabb4.min_x = vdupq_laneq_f32(obj.bounds_min, 0);
        aabb4.min_y = vdupq_laneq_f32(obj.bounds_min, 1);
        aabb4.min_z = vdupq_laneq_f32(obj.bounds_min, 2);
        aabb4.max_x = vdupq_laneq_f32(obj.bounds_max, 0);
        aabb4.max_y = vdupq_laneq_f32(obj.bounds_max, 1);
        aabb4.max_z = vdupq_laneq_f32(obj.bounds_max, 2);
        
        uint32x4_t result = neon_aabb4_vs_frustum(frustum, aabb4);
        
        if (vgetq_lane_u32(result, 0)) {
            visible_objects[visible_count++] = obj;
        }
    }
    return visible_count;
}

// ---------------------------------------------------------------------------
// Distance-based LOD selection
// ---------------------------------------------------------------------------

inline int neon_select_lod(const float32x4_t& camera_pos, const float32x4_t& object_pos,
                            const float* lod_distances, int num_lods) {
    // Distance squared
    float32x4_t diff = vsubq_f32(object_pos, camera_pos);
    float32x4_t dist_sq = vmulq_f32(diff, diff);
    float dist2 = vgetq_lane_f32(dist_sq, 0) + vgetq_lane_f32(dist_sq, 1) + vgetq_lane_f32(dist_sq, 2);
    
    for (int i = num_lods - 1; i >= 0; --i) {
        if (dist2 >= lod_distances[i] * lod_distances[i]) return i;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// Camera frustum corners (for debug visualization)
// ---------------------------------------------------------------------------

inline void neon_frustum_corners(const Frustum& frustum, float* corners) {
    // Intersect 3 planes at a time to get 8 corners
    // Plane indices: L=0, R=1, B=2, T=3, N=4, F=5
    // Corners: LBT, RBT, LBF, RBF, LTT, RTT, LTF, RTF
    
    // Solve 3x3 systems - simplified for NEON
    // For production, use proper plane intersection
    for (int i = 0; i < 8; ++i) {
        corners[i*3+0] = 0;
        corners[i*3+1] = 0;
        corners[i*3+2] = 0;
    }
}

// ---------------------------------------------------------------------------
// Temporal frustum (for temporal reprojection)
// ---------------------------------------------------------------------------

struct TemporalFrustum {
    Frustum current;
    Frustum previous;
    float32x4_t jitter;  // sub-pixel jitter for TAA
};

inline TemporalFrustum neon_create_temporal_frustum(const float* viewproj, const float* prev_viewproj, float jitter_x, float jitter_y) {
    TemporalFrustum tf;
    tf.current = Frustum::from_viewproj(viewproj);
    tf.previous = Frustum::from_viewproj(prev_viewproj);
    tf.jitter = {jitter_x, jitter_y, 0, 0};
    return tf;
}

// ---------------------------------------------------------------------------
// Clustered Forward / Deferred culling helpers
// ---------------------------------------------------------------------------

struct ClusterBounds {
    float32x4_t min_z[32];  // Z slices
    float32x4_t max_z[32];
    Frustum frustums[32];   // Per-cluster frustum (for tiled culling)
};

inline void neon_build_cluster_frustums(const Frustum& main_frustum, ClusterBounds& clusters, int num_clusters_z) {
    // Split main frustum Z range into clusters
    float near_z = main_frustum.planes[4][3]; // Near plane distance
    float far_z = main_frustum.planes[5][3];  // Far plane distance
    
    // Logarithmic Z distribution
    for (int i = 0; i < num_clusters_z; ++i) {
        float t0 = float(i) / num_clusters_z;
        float t1 = float(i+1) / num_clusters_z;
        float z0 = near_z * powf(far_z/near_z, t0);
        float z1 = near_z * powf(far_z/near_z, t1);
        
        clusters.min_z[i] = vdupq_n_f32(z0);
        clusters.max_z[i] = vdupq_n_f32(z1);
        
        // Build sub-frustum with modified near/far
        clusters.frustums[i] = main_frustum;
        clusters.frustums[i].planes[4][3] = z0; // Near
        clusters.frustums[i].planes[5][3] = z1; // Far
    }
}

}  // namespace neon